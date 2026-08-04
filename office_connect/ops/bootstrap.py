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
from datetime import date
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
    Role,
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
from office_connect.core.time import utc_now
from office_connect.core.workflow import get_published_version

# ops is the composition root: it may import modules (import-linter forbids only
# core→modules / core→ops; module seeds live in the module, wiring lives here).
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
_FIXTURE_ACTIVITIES: tuple[dict[str, Any], ...] = (
    {"title": "[fixture] Q1 Health Promotion Planning Workshop",
     "date_start": date(2026, 2, 10), "venue": "BLHSD Conference Room"},
    {"title": "[fixture] Regional Immunization Coverage Review",
     "date_start": date(2026, 3, 5), "venue": "Regional Office"},
    {"title": "[fixture] UHC Integration Site Visit",
     "date_start": date(2026, 4, 18), "venue": "Provincial Health Office"},
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
async def _load_fixtures(session: AsyncSession) -> dict[str, Any]:
    existing_titles = set(
        (await session.execute(select(Activity.title))).scalars().all()
    )
    activities_created: list[str] = []
    for spec in _FIXTURE_ACTIVITIES:
        if spec["title"] not in existing_titles:
            session.add(Activity(**spec))
            activities_created.append(spec["title"])

    # Org tree + staff go through the SAME ingest service the real CSS-IS feed
    # uses (one code path) — the fixture dicts already match the feed schema.
    ingest = await ingest_directory(
        session, org_units=_FIXTURE_ORG_UNITS, staff=_FIXTURE_STAFF
    )

    await session.commit()
    total_activities = (
        await session.execute(select(func.count()).select_from(Activity))
    ).scalar_one()
    return {
        "activities_created": activities_created,
        "activities_total": total_activities,
        "org_units_created": ingest.org_units_created,
        "staff_created": ingest.staff_created,
    }


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
