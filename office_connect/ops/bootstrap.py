"""Bootstrap CLI — prepare a fresh Office-Connect install (Increment 3).

    docker compose exec app python -m office_connect.ops.bootstrap init
    docker compose exec app python -m office_connect.ops.bootstrap create-admin --email a@b --name "..."
    docker compose exec app python -m office_connect.ops.bootstrap load-fixtures
    docker compose exec app python -m office_connect.ops.bootstrap send-test-email --to a@b

Subcommands:

- ``init``          — ensure the tenant config row + the module feature flags
                      exist (idempotent; safe in any environment).
- ``create-admin``  — record the designated System Admin (email + name) into the
                      tenant's non-public ``settings.bootstrap_admin``. This
                      records intent; ``promote-admin`` (below) turns it into a
                      real login. The record is never served by ``/api/v1/config``.
- ``seed-rbac``     — seed the permission + role catalogs and the default
                      role→permission grants (idempotent; any environment — RBAC
                      config is public). Run before ``promote-admin``.
- ``seed-workflows`` — author + publish the module workflow definitions
                      (``reimbursement.claim``). Idempotent: keyed on "a
                      published version exists" — a re-run never mints a new
                      version. Run after ``seed-rbac``.
- ``promote-admin`` — promote ``settings.bootstrap_admin`` into a real break-glass
                      ``core_users`` login (Stage B): Argon2id temp password
                      (forced change on first login) + global ``system_admin``
                      grant. Idempotent. Prints the temp password ONCE (never
                      audited/logged).
- ``load-fixtures`` — load synthetic dev fixtures (sample activities + a small
                      org-unit tree + staff directory — CSS-IS is a separate
                      system, no coupling). **Hard-refused when APP_ENV=production**
                      (never fabricate data in prod).
- ``ingest-directory`` — ingest a CSS-IS-shaped directory CSV feed (``--org-units``
                      / ``--staff`` paths) via the shared ``core.directory`` ingest
                      service; ``--full`` prunes staff absent from the feed.
- ``set-flag``      — flip a module feature flag ON/OFF (R-2-wizard; audited
                      UPDATE through ``oc_app``; the dev-walkthrough + go-live
                      switch — migration/seed defaults stay fail-safe OFF).
- ``pilot-roster``  — report **who can reach the reimbursement module** (R-9).
                      Read-only, safe in production. The flag says whether the
                      module is on; RBAC grants say for whom, and this prints
                      that list — including which holders are AGENCY-WIDE.
- ``send-test-email`` — send a test email through the selected driver (or log in
                      dev) to prove the notification seam is wired.

All DB writes go through the least-privilege ``oc_app`` role via ``OCSession``,
so they are audited (hash chain) exactly like ordinary app writes. Follows the
async-from-sync pattern of ``ops/restore_drill.py`` (a fresh NullPool engine per
command, disposed in ``finally`` — never the app's pooled engine).
"""

import argparse
import asyncio
import json
import sys
from datetime import timedelta
from typing import Any, Awaitable, Callable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# Importing these registers the OCSession audit + soft-delete listeners so the
# bootstrap writes below are hash-chained and soft-delete-filtered.
import office_connect.core.audit  # noqa: F401
import office_connect.core.soft_delete  # noqa: F401
from office_connect.core.config import Settings, get_settings
from office_connect.core.directory import ingest_directory
from office_connect.core.models import (
    Activity,
    FeatureFlag,
    OrgUnit,
    Role,
    Staff,
    TenantConfig,
    User,
    UserRole,
)
from office_connect.core.notifications import send_test_email
from office_connect.core.seeds import apply_all, apply_dataset
from office_connect.core.seeds.rbac import (
    PERMISSIONS_DATASET,
    ROLES_DATASET,
    apply_rbac_grants,
)
from office_connect.core.security import generate_temp_password, hash_password
from office_connect.core.session import OCSession, set_audit_context
from office_connect.core.time import to_manila, utc_now
from office_connect.core.workflow import get_published_version

# ops is the composition root: it may import modules (import-linter forbids only
# core→modules / core→ops; module seeds live in the module, wiring lives here).
from office_connect.modules.reimbursement.fixtures import load_pilot_fixtures
from office_connect.modules.reimbursement.seeds import apply_reimbursement_seeds
from office_connect.modules.reimbursement.workflow import (
    DEFINITION_CODES as REIMB_DEFINITION_CODES,
    ensure_definitions as ensure_reimb_definitions,
)

# Canonical module flags (mirrors migration 0001 seeds — kept in sync on rename).
DEFAULT_FLAGS: tuple[tuple[str, str], ...] = (
    ("module.reimbursement", "Local Travel Reimbursement module"),
    ("module.css_is", "CSS-IS client satisfaction module"),
    ("module.dmwis", "DMWIS document management module"),
)

# Synthetic dev fixtures — clearly non-production sample activities.
#
# Dates are RELATIVE to the run date, for the same reason the reimbursement demo
# trips are: the Calendar of Activities (Stage D-2) opens on *today forward*, and
# three activities hard-coded to Feb–Apr 2026 meant a calendar that was empty on
# first load for most of the year. A demo whose default view shows nothing
# demonstrates nothing.
#
# The spread is deliberate — past (done), current (ongoing), near future
# (planned) and one cancelled — so every `core_activity_status` tone is visible
# on screen rather than only in a test. The two past windows BRACKET the demo
# trips in `modules/reimbursement/fixtures.py`, which link to them by title:
# that is what finally gives `reimb_claims.activity_id` a non-null value and
# makes the connection spine (master-plan §1.2) something you can see.
_FIXTURE_ACTIVITIES: tuple[dict[str, Any], ...] = (
    {"title": "[fixture] Q3 Regional Health Systems Review",
     "start_offset": -42, "duration": 17, "venue": "Regional Office",
     "division_code": "BLHSD-TECH", "status": "done",
     "ppa_code": "300000100001000"},
    {"title": "[fixture] Immunization Coverage Validation",
     "start_offset": -22, "duration": 14, "venue": "Provincial Health Office",
     "division_code": "BLHSD-TECH", "status": "done",
     "ppa_code": "300000100001000"},
    {"title": "[fixture] UHC Integration Site Visits",
     "start_offset": -2, "duration": 7, "venue": "Provincial Health Office",
     "division_code": "BLHSD-TECH", "status": "ongoing",
     "ppa_code": "300000100001000"},
    {"title": "[fixture] Annual Planning Workshop",
     "start_offset": 12, "duration": 2, "venue": "BLHSD Conference Room",
     "division_code": "BLHSD-FIN", "status": "planned",
     "ppa_code": "100000100001000"},
    {"title": "[fixture] Mid-year Coordination Meeting (cancelled)",
     "start_offset": 20, "duration": 0, "venue": "BLHSD Conference Room",
     "division_code": "BLHSD-FIN", "status": "cancelled",
     "ppa_code": "100000100001000"},
    {"title": "[fixture] Year-end Financial Review",
     "start_offset": 40, "duration": 1, "venue": "BLHSD Conference Room",
     "division_code": "BLHSD-FIN", "status": "planned",
     "ppa_code": "100000100001000"},
)

# Synthetic org-unit tree + staff directory — dev/UAT only (CSS-IS is a separate
# system that will feed real person data in later; there is no coupling here).
# Parents precede children so the tree can be built in one pass.
_FIXTURE_ORG_UNITS: tuple[dict[str, Any], ...] = (
    {"code": "BLHSD", "name": "Bureau of Local Health Systems Development",
     "kind": "office", "parent_code": None, "sort_order": 0},
    {"code": "BLHSD-FIN", "name": "Finance & Administrative Division",
     "kind": "division", "parent_code": "BLHSD", "sort_order": 1},
    {"code": "BLHSD-TECH", "name": "Technical Division",
     "kind": "division", "parent_code": "BLHSD", "sort_order": 2},
    {"code": "BLHSD-FIN-ACCT", "name": "Accounting Section",
     "kind": "section", "parent_code": "BLHSD-FIN", "sort_order": 1},
    {"code": "BLHSD-TECH-PLAN", "name": "Planning Section",
     "kind": "section", "parent_code": "BLHSD-TECH", "sort_order": 1},
)
_FIXTURE_STAFF: tuple[dict[str, Any], ...] = (
    {"employee_no": "F-0001", "given_name": "Maria", "surname": "Santos",
     "full_name": "Maria Santos", "email": "maria.santos@example.gov.ph",
     "position_title": "Division Chief", "employment_status": "permanent",
     "division_code": "BLHSD-FIN", "section_code": None},
    {"employee_no": "F-0002", "given_name": "Jose", "surname": "Cruz",
     "full_name": "Jose Cruz", "email": "jose.cruz@example.gov.ph",
     "position_title": "Accountant III", "employment_status": "permanent",
     "division_code": "BLHSD-FIN", "section_code": "BLHSD-FIN-ACCT"},
    {"employee_no": "T-0001", "given_name": "Ana", "surname": "Reyes",
     "full_name": "Ana Reyes", "email": "ana.reyes@example.gov.ph",
     "position_title": "Planning Officer II", "employment_status": "casual",
     "division_code": "BLHSD-TECH", "section_code": "BLHSD-TECH-PLAN"},
)


async def _with_app_session(
    settings: Settings, work: Callable[[AsyncSession], Awaitable[Any]]
) -> Any:
    """Run ``work`` inside an audited ``oc_app`` session on a fresh NullPool
    engine, disposing it afterwards."""
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        sync_session_class=OCSession,
        expire_on_commit=False,
    )
    try:
        async with factory() as session:
            set_audit_context(session, request_id="bootstrap")
            return await work(session)
    finally:
        await engine.dispose()


# --------------------------------------------------------------------- init
async def _init(session: AsyncSession) -> dict[str, Any]:
    tenant = (
        await session.execute(select(TenantConfig).order_by(TenantConfig.id).limit(1))
    ).scalar_one_or_none()
    created_tenant = False
    if tenant is None:  # safety net — normally seeded by migration 0001
        tenant = TenantConfig(name="Office-Connect", short_name="OC")
        session.add(tenant)
        await session.flush()
        created_tenant = True

    existing_keys = set(
        (await session.execute(select(FeatureFlag.key))).scalars().all()
    )
    created_flags: list[str] = []
    for key, description in DEFAULT_FLAGS:
        if key not in existing_keys:
            session.add(FeatureFlag(key=key, enabled=False, description=description))
            created_flags.append(key)
    await session.commit()
    return {
        "tenant_id": tenant.id,
        "tenant_created": created_tenant,
        "flags_created": created_flags,
        "flags_total": len(existing_keys) + len(created_flags),
    }


# -------------------------------------------------------------- create-admin
async def _record_admin(session: AsyncSession, email: str, name: str) -> dict[str, Any]:
    tenant = (
        await session.execute(select(TenantConfig).order_by(TenantConfig.id).limit(1))
    ).scalar_one_or_none()
    if tenant is None:
        raise RuntimeError("no tenant config found — run 'init' first")
    record = {"email": email, "name": name, "recorded_at": utc_now().isoformat()}
    # Reassign (not in-place mutate) so SQLAlchemy detects the JSONB change.
    tenant.settings = {**(tenant.settings or {}), "bootstrap_admin": record}
    await session.commit()
    return {
        "tenant_id": tenant.id,
        "bootstrap_admin": record,
        "note": "recorded for Stage B promotion; not a login (no user table yet)",
    }


# ------------------------------------------------------------- load-fixtures
#: The one dev login that holds NOTHING. Stage D-1's landing shows a person what
#: they can open, and after R-9 established that the cohort IS the grant list
#: (api-standards §9i), "can open nothing" is the COMMON case rather than the
#: edge one — yet every other dev account holds a role, and every seeded role
#: carries at least ``reimb.claim.read``. Without this account the landing's
#: no-access state cannot be driven over real HTTP at all.
#:
#: **Never grant it a role "for convenience later."** Having none is its entire
#: value; the moment it has one, the state it exists to prove is untestable again.
_NO_GRANTS_EMAIL = "no-grants@doh.gov"
_NO_GRANTS_PASSWORD = "BoardSmoke!2026x"  # matches the other dev smoke accounts


async def _ensure_no_grants_account(session: AsyncSession) -> dict[str, Any]:
    """Idempotently create the grant-less landing-smoke login."""
    existing = (
        await session.execute(select(User).where(User.email == _NO_GRANTS_EMAIL))
    ).scalar_one_or_none()
    if existing is not None:
        live_grants = (
            await session.execute(
                select(func.count()).select_from(UserRole).where(
                    UserRole.user_id == existing.id
                )
            )
        ).scalar_one()
        return {"email": _NO_GRANTS_EMAIL, "created": False, "role_grants": live_grants}

    session.add(
        User(
            email=_NO_GRANTS_EMAIL,
            password_hash=hash_password(_NO_GRANTS_PASSWORD),
            is_active=True,
            # Not pending: the point is to reach the LANDING, and a pending
            # session is redirected to the password screen before it renders.
            must_change_password=False,
        )
    )
    return {"email": _NO_GRANTS_EMAIL, "created": True, "role_grants": 0}


# ------------------------------------------------------- the smoke cohort
#: The five *granted* dev logins that drive live smoke, alongside the grant-less
#: account above. Every recent session's live smoke is run as these chairs:
#: a global overseer, a scoped overseer, a traveller, a stranger, an approver.
#:
#: **They live here because a `docker compose down -v` at Stage D-2 destroyed
#: them and nothing in the repository could bring them back.** Five accounts
#: PROGRESS.md described in prose had been minted by hand in earlier sessions;
#: only ``no-grants@doh.gov`` (#29) was reproducible, and it was reproducible
#: precisely because someone had hit this wall once already. A cohort described
#: in a document is not a cohort — the same lesson ``_backdated`` learned about
#: docstrings that ask callers to clean up.
#:
#: The tree is deliberately SEPARATE from the BLHSD fixture tree: smoke asserts
#: that a scoped officer in one office cannot see another office's work, which
#: needs two offices that genuinely do not contain one another.
_SMOKE_ORG_UNITS: tuple[dict[str, Any], ...] = (
    {"code": "SMOKE-A", "name": "Smoke Office A", "kind": "office",
     "parent_code": None, "sort_order": 10},
    {"code": "SMOKE-A1", "name": "Smoke Division A1", "kind": "division",
     "parent_code": "SMOKE-A", "sort_order": 11},
    {"code": "SMOKE-B", "name": "Smoke Office B", "kind": "office",
     "parent_code": None, "sort_order": 12},
    # Staff must sit in a DIVISION (ingest refuses an office), and the scoped
    # officer is granted on the OFFICE above it on purpose: that makes the
    # smoke assert `descendants_or_self`, not just an equality on one unit.
    {"code": "SMOKE-B1", "name": "Smoke Division B1", "kind": "division",
     "parent_code": "SMOKE-B", "sort_order": 13},
)
_SMOKE_STAFF: tuple[dict[str, Any], ...] = (
    {"employee_no": "SMK-A-1", "given_name": "Smoke", "surname": "Traveller-A",
     "full_name": "Smoke Traveller-A", "email": "board-traveller@doh.gov",
     "position_title": "Health Program Officer II",
     "employment_status": "permanent",
     "division_code": "SMOKE-A1", "section_code": None},
    {"employee_no": "SMK-B-1", "given_name": "Smoke", "surname": "Traveller-B",
     "full_name": "Smoke Traveller-B", "email": "smoke-b-traveller@doh.gov",
     "position_title": "Health Program Officer II",
     "employment_status": "permanent",
     "division_code": "SMOKE-B1", "section_code": None},
)

#: ``(email, role_code, scope_org_unit_code, staff_employee_no)``.
#: ``scope_org_unit_code=None`` with a role means a GLOBAL grant.
_SMOKE_ACCOUNTS: tuple[tuple[str, str, str | None, str | None], ...] = (
    ("board-smoke@doh.gov", "admin_officer", None, None),
    ("scoped-officer@doh.gov", "admin_officer", "SMOKE-B", None),
    ("smoke-approver-a@doh.gov", "approver", "SMOKE-A1", None),
    ("board-traveller@doh.gov", "staff", None, "SMK-A-1"),
    ("smoke-b-traveller@doh.gov", "staff", None, "SMK-B-1"),
)


async def _ensure_smoke_cohort(session: AsyncSession) -> dict[str, Any]:
    """Idempotently create the five granted dev smoke logins and their scopes.

    Requires ``seed-rbac`` (the roles must exist). Re-running changes nothing:
    an existing user is left exactly as it is, grants included — this must never
    "repair" an account someone deliberately altered mid-smoke.
    """
    ingest = await ingest_directory(
        session, org_units=_SMOKE_ORG_UNITS, staff=_SMOKE_STAFF
    )
    await session.flush()

    units = {
        code: unit_id
        for code, unit_id in (
            await session.execute(select(OrgUnit.code, OrgUnit.id))
        ).all()
    }
    staff_ids = {
        no: sid
        for no, sid in (
            await session.execute(select(Staff.employee_no, Staff.id))
        ).all()
    }
    roles = {
        code: role_id
        for code, role_id in (await session.execute(select(Role.code, Role.id))).all()
    }

    created: list[str] = []
    for email, role_code, scope_code, employee_no in _SMOKE_ACCOUNTS:
        existing = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if existing is not None:
            continue
        if role_code not in roles:
            raise RuntimeError(
                f"role {role_code!r} does not exist — run 'seed-rbac' before "
                "'load-fixtures' so the smoke cohort has roles to be granted"
            )
        user = User(
            email=email,
            password_hash=hash_password(_NO_GRANTS_PASSWORD),
            is_active=True,
            must_change_password=False,
            staff_id=staff_ids.get(employee_no) if employee_no else None,
        )
        session.add(user)
        await session.flush()
        session.add(
            UserRole(
                user_id=user.id,
                role_id=roles[role_code],
                # NULL org_unit_id is the global grant — the shape system_admin
                # and the board's global officer both rely on.
                org_unit_id=units.get(scope_code) if scope_code else None,
            )
        )
        created.append(email)

    return {
        "created": created,
        "total": len(_SMOKE_ACCOUNTS),
        "org_units_created": ingest.org_units_created,
        "staff_created": ingest.staff_created,
    }


async def _load_fixtures(session: AsyncSession) -> dict[str, Any]:
    # Org tree + staff go through the SAME ingest service the real CSS-IS feed
    # uses (one code path) — the fixture dicts already match the feed schema.
    # Ingested FIRST so the activities below can resolve their division codes.
    ingest = await ingest_directory(
        session, org_units=_FIXTURE_ORG_UNITS, staff=_FIXTURE_STAFF
    )
    await session.flush()

    units = {
        code: unit_id
        for code, unit_id in (
            await session.execute(select(OrgUnit.code, OrgUnit.id))
        ).all()
    }
    today = to_manila(utc_now()).date()
    existing_titles = set(
        (await session.execute(select(Activity.title))).scalars().all()
    )
    activities_created: list[str] = []
    for spec in _FIXTURE_ACTIVITIES:
        if spec["title"] in existing_titles:
            continue
        start = today + timedelta(days=spec["start_offset"])
        session.add(
            Activity(
                title=spec["title"],
                date_start=start,
                # duration 0 = a single-day activity, which is `date_end IS NULL`
                # rather than an end equal to the start: the calendar's overlap
                # predicate coalesces the two, and NULL is the shape the column
                # already uses for "one day".
                date_end=(
                    start + timedelta(days=spec["duration"])
                    if spec["duration"]
                    else None
                ),
                venue=spec["venue"],
                status=spec["status"],
                ppa_code=spec.get("ppa_code"),
                division_id=units.get(spec["division_code"]),
            )
        )
        activities_created.append(spec["title"])
    no_grants = await _ensure_no_grants_account(session)
    smoke = await _ensure_smoke_cohort(session)

    await session.commit()
    total_activities = (
        await session.execute(select(func.count()).select_from(Activity))
    ).scalar_one()
    return {
        "activities_created": activities_created,
        "activities_total": total_activities,
        "org_units_created": ingest.org_units_created + smoke["org_units_created"],
        "staff_created": ingest.staff_created + smoke["staff_created"],
        "no_grants_account": no_grants,
        "smoke_cohort": smoke,
    }


# ------------------------------------------------------- load-pilot-fixtures
async def _with_pilot_fixtures(settings: Settings) -> dict[str, Any]:
    """Run the module's demo-cast builder and commit.

    Thin wrapper rather than a body: the cast itself lives in
    ``modules/reimbursement/fixtures.py`` because it is the module's knowledge
    (its claim shapes, its computation, its §14 list). ops owns the wiring and
    the environment refusal — the same split ``seed-workflows`` follows.
    """
    async def _work(session: AsyncSession) -> dict[str, Any]:
        result = await load_pilot_fixtures(session)
        await session.commit()
        return result

    return await _with_app_session(settings, _work)


# --------------------------------------------------------------- seed-rbac
async def _seed_rbac(session: AsyncSession) -> dict[str, Any]:
    """Idempotently seed the permission + role catalogs and the default
    role→permission grants (auth-rbac-onprem.md). Safe in any environment —
    RBAC config is public, not synthetic data."""
    permissions = await apply_dataset(session, PERMISSIONS_DATASET)
    roles = await apply_dataset(session, ROLES_DATASET)
    grants = await apply_rbac_grants(session)
    await session.commit()
    return {"permissions": permissions, "roles": roles, "grants": grants}


# ------------------------------------------------------------ promote-admin
async def _promote_admin(session: AsyncSession) -> dict[str, Any]:
    """Promote the recorded ``bootstrap_admin`` into a real break-glass login.

    Reads ``core_tenant_configs.settings['bootstrap_admin']`` (written by
    ``create-admin``), creates one ``core_users`` row with an Argon2id-hashed
    temporary password (forced change on first login), and grants ``system_admin``
    globally. Idempotent: a second run finds the live account and no-ops. The
    temporary password is printed ONCE — it is never audited (redacted) or
    logged. Requires ``seed-rbac`` (the ``system_admin`` role must exist)."""
    tenant = (
        await session.execute(select(TenantConfig).order_by(TenantConfig.id).limit(1))
    ).scalar_one_or_none()
    if tenant is None:
        raise RuntimeError("no tenant config found — run 'init' first")
    record = (tenant.settings or {}).get("bootstrap_admin")
    if not record:
        raise RuntimeError("no bootstrap_admin recorded — run 'create-admin' first")
    email = record["email"]
    name = record.get("name")

    existing = (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    if existing is not None:
        return {
            "user_id": existing.id,
            "email": email,
            "created": False,
            "note": "already promoted — no change",
        }

    role = (
        await session.execute(select(Role).where(Role.code == "system_admin"))
    ).scalar_one_or_none()
    if role is None:
        raise RuntimeError("system_admin role not seeded — run 'seed-rbac' first")

    temp_password = generate_temp_password()
    user = User(
        email=email,
        password_hash=hash_password(temp_password),
        must_change_password=True,
        is_active=True,
        is_break_glass=True,
        auth_source="local",
        staff_id=None,
    )
    session.add(user)
    await session.flush()  # assign user.id for the grant
    session.add(UserRole(user_id=user.id, role_id=role.id, org_unit_id=None))
    await session.commit()
    return {
        "user_id": user.id,
        "email": email,
        "name": name,
        "created": True,
        "role": "system_admin (global)",
        "temporary_password": temp_password,
        "note": "log in and change this password immediately "
        "(must_change_password=true); it is shown here once and never logged",
    }


# ------------------------------------------------------------ load-reference
async def _load_reference(
    session: AsyncSession, app_env: str, only: set[str] | None
) -> dict[str, Any]:
    """Idempotent, environment-aware upsert of the reference datasets.

    A full run (no ``--dataset`` filter) also applies the module-owned
    reference seeds (R-4-app closed the "module seeds only run from tests"
    gap): reimbursement DTE rates / region clusters / config pack — public
    legal config, safe in any environment."""
    results = await apply_all(session, app_env=app_env, only=only)
    module_results: dict[str, Any] = {}
    if only is None:
        module_results["reimbursement"] = await apply_reimbursement_seeds(session)
    await session.commit()
    return {"app_env": app_env, "datasets": results, "module_datasets": module_results}


# ------------------------------------------------------------ seed-workflows
async def _seed_workflows(session: AsyncSession) -> dict[str, Any]:
    """Idempotently author + publish the module workflow definitions
    (``reimbursement.claim`` + ``reimbursement.liquidation``). A re-run NEVER
    mints a new version — a chain change is an explicit authored v2 (e.g. the
    DO 2019-0225 tiered chain). Canonical sequence: init → load-reference →
    seed-rbac → seed-workflows → promote-admin.

    Reports per definition, and reports ``created`` per definition rather than
    for the batch: a tenant seeded before R-6-liq-chain has the claim chain
    already and gains only the liquidation one, and a summary that said
    "created: false" for that run would hide the new chain entirely."""
    codes = sorted(set(REIMB_DEFINITION_CODES.values()))
    before = {
        code: await get_published_version(session, code) for code in codes
    }
    await ensure_reimb_definitions(session)
    await session.commit()
    return {
        "definitions": [
            {
                "definition": code,
                "version_no": (
                    await get_published_version(session, code)
                ).version_no,
                "created": before[code] is None,
            }
            for code in codes
        ]
    }


# ------------------------------------------------------------------ set-flag
async def _set_flag(session: AsyncSession, key: str, enabled: bool) -> dict[str, Any]:
    """Flip a module feature flag (dev walkthroughs / go-live). Refuses keys
    that neither exist nor appear in ``DEFAULT_FLAGS`` (typo guard). The write
    rides the audited ``oc_app`` session (hash-chained UPDATE); the fail-safe
    OFF defaults in migrations/seeds are untouched. ``/api/v1/config``'s 30 s
    Redis TTL picks the change up on its own — no cache invalidation here."""
    row = (
        await session.execute(select(FeatureFlag).where(FeatureFlag.key == key))
    ).scalar_one_or_none()
    known = dict(DEFAULT_FLAGS)
    if row is None and key not in known:
        raise RuntimeError(
            f"unknown flag '{key}' — pass an existing key or one of "
            f"{sorted(known)}"
        )
    was = bool(row and row.enabled and row.is_active)
    if row is None:
        row = FeatureFlag(key=key, enabled=enabled, description=known[key])
        session.add(row)
    else:
        row.enabled = enabled
        if enabled and not row.is_active:
            row.is_active = True
    await session.commit()
    return {
        "key": key,
        "was": was,
        "now": bool(row.enabled and row.is_active),
        "note": "the /api/v1/config cache TTL is 30 s — clients see it within that",
    }


# --------------------------------------------------------------- pilot-roster
#: The permission prefix that defines the reimbursement pilot cohort. Anyone
#: holding any of these can reach some part of the module; nobody else can.
_PILOT_PREFIX = "reimb."


async def _pilot_roster(
    session: AsyncSession, prefix: str, limit: int
) -> dict[str, Any]:
    """**Who is in the pilot right now** — spec §14's *"flag ON for pilot cohort
    only"*, answered as a report rather than as a schema.

    R-9's confirmed posture (see api-standards §9i): the feature flag answers
    *"is this module on"* and RBAC grants answer *"for whom"*. Those are two
    different questions and conflating them is what a per-cohort flag column
    would do. Nothing in this codebase auto-assigns a role — there is no default
    grant path anywhere — so the set of people who can reach the module is
    exactly the set of people an administrator granted a role to. The cohort is
    therefore already precise; what it was missing is a way to READ it.

    That gap is the real risk, and it is worth naming plainly: a cohort you
    cannot enumerate is a cohort you cannot verify, and "the pilot" silently
    becoming "the agency" would look like nothing at all. One global ``staff``
    grant to somebody outside the pilot is all it takes. This command is the
    control that makes it visible, so run it before go-live and after any grant
    change.

    Read-only, and safe in production — it prints role/permission metadata and
    the actor's login email, never claim data.
    """
    from office_connect.core.models import OrgUnit, Permission, RolePermission

    flag = (
        await session.execute(
            select(FeatureFlag).where(FeatureFlag.key == "module.reimbursement")
        )
    ).scalar_one_or_none()

    now = utc_now()
    rows = (
        await session.execute(
            select(
                User.id,
                User.email,
                User.is_active,
                Role.code,
                UserRole.org_unit_id,
                OrgUnit.name,
                UserRole.valid_from,
                UserRole.valid_to,
                Permission.code,
            )
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .join(RolePermission, RolePermission.role_id == Role.id)
            .join(Permission, Permission.id == RolePermission.permission_id)
            .join(OrgUnit, OrgUnit.id == UserRole.org_unit_id, isouter=True)
            .where(Permission.code.startswith(prefix))
            .order_by(User.email, Role.code, Permission.code)
        )
    ).all()

    members: dict[int, dict[str, Any]] = {}
    for (
        user_id, email, is_active, role_code, org_unit_id, org_unit_name,
        valid_from, valid_to, perm_code,
    ) in rows:
        # A grant outside its validity window grants nothing (delegation/OIC),
        # so it must not appear as pilot membership — the roster has to match
        # what the app would actually authorize, not what the table records.
        if (valid_from is not None and valid_from > now) or (
            valid_to is not None and valid_to <= now
        ):
            continue
        member = members.setdefault(
            user_id,
            {
                "user_id": user_id,
                "email": email,
                "login_active": bool(is_active),
                "grants": [],
                "permissions": set(),
            },
        )
        member["permissions"].add(perm_code)
        grant = {
            "role": role_code,
            # NULL org unit = AGENCY-WIDE. Spelled out because it is the single
            # most consequential cell in this report: an agency-wide review
            # grant is what lets someone promote a return reason into a warning
            # every claimant in the tenant sees (api-standards §9h).
            "scope": org_unit_name if org_unit_id is not None else "AGENCY-WIDE",
            "org_unit_id": org_unit_id,
            "valid_from": valid_from,
            "valid_to": valid_to,
        }
        if grant not in member["grants"]:
            member["grants"].append(grant)

    roster = []
    for member in members.values():
        member["permissions"] = sorted(member["permissions"])
        roster.append(member)
    roster.sort(key=lambda m: m["email"])

    agency_wide = [
        m["email"]
        for m in roster
        if any(g["org_unit_id"] is None for g in m["grants"])
    ]
    # "State what the page is hiding" (api-standards §9f), applied to a report:
    # the COUNTS always describe the whole cohort and only the detail list is
    # capped, so a truncated roster can never read as a small pilot. `limit=0`
    # means no cap.
    shown = roster if limit <= 0 else roster[:limit]
    return {
        "flag": {
            "key": "module.reimbursement",
            "on": bool(flag and flag.enabled and flag.is_active),
        },
        "cohort_size": len(roster),
        "agency_wide_count": len(agency_wide),
        "agency_wide_holders": sorted(agency_wide)[: (limit if limit > 0 else None)],
        "members_shown": len(shown),
        "members": shown,
        "note": (
            "The flag answers 'is this module on'; these grants answer 'for "
            "whom'. Nothing auto-assigns a role, so this list IS the pilot "
            "cohort. Review agency_wide_holders especially — an agency-wide "
            "reimb.claim.review grant can promote a return reason into a "
            "warning shown to every claimant in the tenant (api-standards §9h). "
            "cohort_size and agency_wide_count are never capped; only the "
            "members detail is (--limit, 0 = all)."
        ),
    }


# --------------------------------------------------------- ingest-directory
def _read_directory_csv(path: str | None) -> list[dict[str, Any]]:
    """Parse a directory CSV file into row mappings (transport-only; the core
    ingest service is format-agnostic). Tolerates a UTF-8 BOM."""
    import csv

    if not path:
        return []
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return [dict(row) for row in csv.DictReader(fh)]


async def _ingest_directory_cli(
    session: AsyncSession,
    org_units_path: str | None,
    staff_path: str | None,
    prune: bool,
) -> dict[str, Any]:
    """Ingest a CSS-IS-shaped directory CSV feed (org units + staff)."""
    result = await ingest_directory(
        session,
        org_units=_read_directory_csv(org_units_path),
        staff=_read_directory_csv(staff_path),
        deactivate_absent=prune,
    )
    await session.commit()
    return {
        "org_units_created": result.org_units_created,
        "org_units_updated": result.org_units_updated,
        "org_units_restored": result.org_units_restored,
        "staff_created": result.staff_created,
        "staff_updated": result.staff_updated,
        "staff_restored": result.staff_restored,
        "staff_deactivated": result.staff_deactivated,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="office_connect.ops.bootstrap",
        description="Prepare a fresh Office-Connect install (Increment 3).",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="ensure tenant + feature flags exist (idempotent)")
    admin = sub.add_parser(
        "create-admin", help="record the first System Admin (promoted at Stage B)"
    )
    admin.add_argument("--email", required=True)
    admin.add_argument("--name", required=True)
    sub.add_parser(
        "load-fixtures", help="load synthetic dev fixtures (refused in production)"
    )
    sub.add_parser(
        "load-pilot-fixtures",
        help="load the spec §14 reimbursement demo cast — 6 travellers, 10 "
        "trips, an aged cash advance (refused in production)",
    )
    ref = sub.add_parser(
        "load-reference",
        help="upsert reference data (idempotent, environment-aware; all envs)",
    )
    ref.add_argument(
        "--dataset", action="append", help="limit to dataset name(s); repeatable"
    )
    sub.add_parser(
        "seed-rbac",
        help="seed the permission/role catalogs + default grants (idempotent)",
    )
    sub.add_parser(
        "seed-workflows",
        help="author + publish the module workflow definitions (idempotent; "
        "a re-run never mints a new version)",
    )
    sub.add_parser(
        "promote-admin",
        help="promote the recorded bootstrap admin into a break-glass login",
    )
    ingest = sub.add_parser(
        "ingest-directory",
        help="ingest a CSS-IS-shaped directory CSV feed (org units + staff)",
    )
    ingest.add_argument("--org-units", help="path to org_units.csv")
    ingest.add_argument("--staff", help="path to staff.csv")
    ingest.add_argument(
        "--full",
        action="store_true",
        help="prune: soft-delete live staff absent from the feed (default: off)",
    )
    flag = sub.add_parser(
        "set-flag",
        help="flip a module feature flag (e.g. set-flag module.reimbursement --on)",
    )
    flag.add_argument("key", help="feature flag key, e.g. module.reimbursement")
    onoff = flag.add_mutually_exclusive_group(required=True)
    onoff.add_argument("--on", action="store_true", help="enable the flag")
    onoff.add_argument("--off", action="store_true", help="disable the flag")
    roster = sub.add_parser(
        "pilot-roster",
        help="report who can reach the reimbursement module (read-only; the "
        "pilot cohort IS the grant list — api-standards §9i)",
    )
    roster.add_argument(
        "--prefix",
        default=_PILOT_PREFIX,
        help=f"permission prefix defining the cohort (default: {_PILOT_PREFIX})",
    )
    roster.add_argument(
        "--limit",
        type=int,
        default=200,
        help="cap the members detail (0 = all); the COUNTS are never capped",
    )
    mail = sub.add_parser(
        "send-test-email", help="send a test email via the selected driver"
    )
    mail.add_argument("--to", required=True)
    args = parser.parse_args(argv)

    settings = get_settings()

    if args.command == "init":
        result = asyncio.run(_with_app_session(settings, _init))
    elif args.command == "create-admin":
        result = asyncio.run(
            _with_app_session(
                settings, lambda s: _record_admin(s, args.email, args.name)
            )
        )
    elif args.command == "load-fixtures":
        if settings.app_env == "production":
            print(
                "refusing to load fixtures in production (APP_ENV=production)",
                file=sys.stderr,
            )
            return 1
        result = asyncio.run(_with_app_session(settings, _load_fixtures))
    elif args.command == "load-pilot-fixtures":
        # Same hard refusal as `load-fixtures`, for the same reason and with
        # more at stake: this one writes claims and a cash advance, i.e. money
        # records, and a synthetic ₱18,000 advance in a real ledger is not a
        # tidy-up job.
        if settings.app_env == "production":
            print(
                "refusing to load pilot fixtures in production "
                "(APP_ENV=production)",
                file=sys.stderr,
            )
            return 1
        result = asyncio.run(_with_pilot_fixtures(settings))
    elif args.command == "load-reference":
        only = set(args.dataset) if args.dataset else None
        result = asyncio.run(
            _with_app_session(
                settings, lambda s: _load_reference(s, settings.app_env, only)
            )
        )
    elif args.command == "seed-rbac":
        result = asyncio.run(_with_app_session(settings, _seed_rbac))
    elif args.command == "seed-workflows":
        result = asyncio.run(_with_app_session(settings, _seed_workflows))
    elif args.command == "promote-admin":
        result = asyncio.run(_with_app_session(settings, _promote_admin))
    elif args.command == "set-flag":
        result = asyncio.run(
            _with_app_session(settings, lambda s: _set_flag(s, args.key, args.on))
        )
    elif args.command == "pilot-roster":
        result = asyncio.run(
            _with_app_session(
                settings, lambda s: _pilot_roster(s, args.prefix, args.limit)
            )
        )
    elif args.command == "ingest-directory":
        result = asyncio.run(
            _with_app_session(
                settings,
                lambda s: _ingest_directory_cli(
                    s, args.org_units, args.staff, args.full
                ),
            )
        )
    else:  # send-test-email
        result = send_test_email(args.to, settings=settings)

    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
