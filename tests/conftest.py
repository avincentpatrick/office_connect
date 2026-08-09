"""Phase-0 QA-gate fixtures.

Canonical invocation (docs/modules/foundation.md §6):

    docker compose exec app pytest -q

Tests run against the compose Postgres/Redis. The suite leaves benign test
rows behind in the dev DB (never tampered data — tamper tests roll back);
``docker compose down -v`` resets everything.
"""

import secrets
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from office_connect.core.config import get_settings
from office_connect.core.db import SessionLocal


# Repo root (holds alembic.ini) — makes the alembic CLI calls cwd-independent.
REPO_ROOT = Path(__file__).resolve().parents[1]

# Shared default for auth fixtures (long + not blocklisted → passes the policy).
DEFAULT_TEST_PASSWORD = "correct-horse-battery-staple"

# The CSRF custom-header contract (api-standards §6) — any non-empty value works.
CSRF = {"X-Requested-With": "1"}


async def login(client, user, password, mfa_secret=None):
    """Log ``user`` in over HTTP (handles the MFA hop when enabled). Promoted
    at R-2-wizard so new HTTP test modules import it (``from tests.conftest
    import CSRF, login``) instead of re-declaring a per-file copy; the six
    pre-existing duplicates are left untouched (zero churn on a green suite)."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"identifier": user.email, "password": password},
        headers=CSRF,
    )
    if resp.json().get("status") == "mfa_required":
        import pyotp

        resp = await client.post(
            "/api/v1/auth/mfa/verify",
            json={
                "mfa_token": resp.json()["mfa_token"],
                "code": pyotp.TOTP(mfa_secret).now(),
            },
            headers=CSRF,
        )
    return resp


@pytest.fixture(scope="session", autouse=True)
def migrated_db():
    """Upgrade to head once before the suite (idempotency is itself a test)."""
    result = subprocess.run(
        ["alembic", "upgrade", "head"], capture_output=True, text=True, cwd=REPO_ROOT
    )
    assert result.returncode == 0, result.stderr


# --- seed guard (R-9): the fourth recurrence stops being a matter of memory ---

#: Columns worth guarding that the seed no longer ASSERTS but the suite can
#: still mutate. ``promoted_check`` is the R-8 lesson in one line: the key was
#: deliberately removed from the seed rows (leaving it there would have made
#: every ``seed`` run demote every promotion), which also removed it from any
#: guard derived from the row dicts. A promotion leaked by a test is invisible
#: except as a warning every later test's wizard silently carries.
_GUARDED_EXTRA_COLUMNS: dict[str, tuple[str, ...]] = {
    "reimb_return_reason_catalogs": ("promoted_check",),
}


def _guarded_datasets():
    from office_connect.core.seeds.datasets import REGISTRY
    from office_connect.modules.reimbursement.seeds import REIMBURSEMENT_DATASETS

    return (*REGISTRY, *REIMBURSEMENT_DATASETS)


async def _snapshot_seeds() -> dict[str, dict]:
    """Every seeded row's mutable columns, keyed by dataset + natural key."""
    from sqlalchemy import select

    engine = create_async_engine(
        get_settings().migration_database_url, poolclass=NullPool
    )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    snapshot: dict[str, dict] = {}
    try:
        async with factory() as session:
            for dataset in _guarded_datasets():
                table = dataset.model.__table__
                wanted = set(dataset.natural_key)
                for row in dataset.rows:
                    wanted |= set(row)
                wanted |= set(_GUARDED_EXTRA_COLUMNS.get(table.name, ()))
                columns = [table.c[name] for name in sorted(wanted) if name in table.c]
                if not columns:
                    continue
                key_cols = [table.c[name] for name in dataset.natural_key]
                # The DECLARED rows only — the ones the dataset actually ships.
                # Tests legitimately create their own holidays, PAP codes and
                # activity tags in these same tables (with randomized keys), and
                # those are not seed drift: this guard is about shape (c),
                # "a fixture mutated SHARED SEEDED DATA", not about every row
                # that happens to live in a table a seed also writes to. Scoping
                # to the declared keys is what makes the failure message mean
                # exactly one thing when it fires.
                declared = {
                    tuple(row[name] for name in dataset.natural_key)
                    for row in dataset.rows
                    if all(name in row for name in dataset.natural_key)
                }
                if not declared:
                    continue
                stmt = select(*columns)
                # LIVE rows only. This session is the migration role with no
                # OCSession listeners, so the global soft-delete filter does not
                # apply and a properly RETIRED row (rule 6 — retired, never
                # deleted) would otherwise read as drift. Retiring a genuinely
                # seeded row still shows up, as a "row disappeared" — which is
                # exactly the shape-(c) bug this guard is for.
                if "deleted_at" in table.c:
                    stmt = stmt.where(table.c.deleted_at.is_(None))
                for record in (await session.execute(stmt)).mappings():
                    key = tuple(record[c.name] for c in key_cols)
                    if key not in declared:
                        continue
                    snapshot[f"{table.name}{key}"] = dict(record)
    finally:
        await engine.dispose()
    return snapshot


@pytest.fixture(scope="session", autouse=True)
def seed_guard(migrated_db):
    """Fail the RUN if the suite left seeded reference data modified.

    **This is the fourth recurrence of one disease, finally made mechanical.**
    Sessions #24–#27 each lost time to a fixture that changed shared state and
    did not put it back, in three different costumes: a holiday row, aged
    ``holder_since`` values, and a promoted return reason. Every time, the fix
    was a ``finally`` and a docstring telling the next person to remember. The
    fourth time is the one where you stop asking people to remember.

    Seed rows are the shared state that matters most, because they are *config*:
    a promoted reason changes what every claimant sees, a flipped
    ``is_active`` changes which checklist items are required, and a changed
    config value changes the money. None of that announces itself — the symptom
    is a later test failing for a reason that has nothing to do with it, or
    worse, a dev database that quietly disagrees with production.

    **Scope: the rows the datasets DECLARE, and only those.** An earlier version
    of this guard watched whole tables, reported fifteen test-created rows and
    said nothing useful. Narrowing it to the declared natural keys is what makes
    a failure here mean exactly one thing: *shared config was changed and not
    changed back*.

    ⚠ **That narrowing is a blind spot, and ``seed_addition_guard`` below is the
    other half.** This fixture said those test-created holidays and PAP codes
    were "ordinary test data, not seed drift". #29 is the evidence that they are
    a defect of their own: they never leave, and 48 of them in
    ``core_compliance_deadlines`` are what made three suite runs fail three
    different ways. The two guards are deliberately separate because they
    diagnose different diseases — this one *mutation*, that one *accumulation*.

    Session-scoped and synchronous on purpose: ``asyncio.run`` at setup and
    teardown runs outside any test's event loop, so this cannot interact with
    ``_dispose_engine_pool``. Reads through the migration role, which is
    read-only usage here.

    A legitimate seed CHANGE (a new circular revision, an edited rate) is made
    by editing the dataset and re-running ``load-reference``; this fixture
    snapshots *after* migrations have run, so an intentional change is inside
    the baseline and passes. What fails is a change made DURING the run.
    """
    import asyncio

    before = asyncio.run(_snapshot_seeds())
    yield
    after = asyncio.run(_snapshot_seeds())

    drifted = []
    for key, values in before.items():
        now = after.get(key)
        if now is None:
            drifted.append(f"{key}: row disappeared")
            continue
        for column, was in values.items():
            if now[column] != was:
                drifted.append(f"{key}.{column}: {was!r} -> {now[column]!r}")
    for key in after.keys() - before.keys():
        # A DECLARED row that did not exist at session start and does now: the
        # suite re-seeded something it had removed, or resurrected a retired row.
        drifted.append(f"{key}: seeded row appeared during the run")

    assert not drifted, (
        "seeded reference data was modified by the test run and not restored:\n  "
        + "\n  ".join(sorted(drifted))
        + "\n\nA fixture that mutates SHARED SEEDED DATA must undo itself — see "
        "`_promoted` in tests/test_reimb_api_insights.py for the shape. Restore "
        "it in a `finally` or a context manager, not at the end of the happy "
        "path (a failing assertion skips that)."
    )


# --- seed ADDITION guard (Stage D closeout): the #29 blind spot, closed -------

#: Seeded tables a run is allowed to GROW, table name → the reason why.
#:
#: **It ships empty, and that is the whole point.** A seeded reference table is
#: config, not scratch space: every row a test leaves behind is read by every
#: later test and by the dev database forever after. Adding an entry here is
#: choosing to let a table accumulate — it needs a reason someone else can
#: audit, not just a green suite.
_ADD_GUARD_EXEMPT: dict[str, str] = {}


async def _snapshot_seed_keys() -> dict[str, set[tuple]]:
    """Every LIVE natural key in each seeded table, keyed by table name.

    Cheaper than ``_snapshot_seeds``: only the natural-key columns are selected,
    because a key set is all an addition can be detected from. Same connection
    posture for the same reasons (migration role, ``NullPool``, disposed in a
    ``finally``, live rows only).
    """
    from sqlalchemy import select

    engine = create_async_engine(
        get_settings().migration_database_url, poolclass=NullPool
    )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    snapshot: dict[str, set[tuple]] = {}
    try:
        async with factory() as session:
            for dataset in _guarded_datasets():
                table = dataset.model.__table__
                if table.name in _ADD_GUARD_EXEMPT:
                    continue
                key_cols = [table.c[name] for name in dataset.natural_key]
                stmt = select(*key_cols)
                # LIVE rows only — which is also what makes soft delete a valid
                # undo. The unique indexes on these tables are partial on
                # `deleted_at IS NULL`, so a test that takes its row back by
                # soft-deleting it both frees the key and reads as clean here.
                if "deleted_at" in table.c:
                    stmt = stmt.where(table.c.deleted_at.is_(None))
                keys = snapshot.setdefault(table.name, set())
                for record in (await session.execute(stmt)).all():
                    keys.add(tuple(record))
    finally:
        await engine.dispose()
    return snapshot


@pytest.fixture(scope="session", autouse=True)
def seed_addition_guard(migrated_db):
    """Fail the RUN if the suite ADDED rows to a seeded reference table.

    **This is the #29 blind spot, and ``seed_guard`` structurally cannot see
    it.** That guard diffs the rows each dataset DECLARES, so it catches a
    seeded row modified and not restored — exactly the job it was built for at
    #28. A row added under a FRESH natural key was invisible to it. Forty-eight
    hash-suffixed ``csmr_to_arta_<hash>`` rows in ``core_compliance_deadlines``
    against 22 real seeds is what that blind spot looked like, and it is why
    three runs at #29 each failed a *different* set of tests while nothing about
    the code changed. Nobody could see it because nothing was watching.

    **A key-set diff, not a row diff.** The question is only *did this table
    grow*, so the failure is loud and the diagnosis is one sentence. What the
    added keys look like usually names the culprit outright — they are literal
    values, so they are greppable.

    **It fails the RUN, not the offending test, and that is a cost decision.**
    Snapshotting 13 tables around each of ~1000 tests is unaffordable, and a
    per-test snapshot would have to run inside that test's event loop — the
    precise collision with ``_dispose_engine_pool`` that both guards are shaped
    to avoid (see ``seed_guard``'s docstring). Session teardown is what this
    check can afford, so session teardown is where it lives.

    The fix for a failure is never an exemption: it is for the test to take its
    row back, with ``owned_row`` — soft delete in a ``finally``, so a failing
    assertion cannot skip the undo.
    """
    import asyncio

    before = asyncio.run(_snapshot_seed_keys())
    yield
    after = asyncio.run(_snapshot_seed_keys())

    added: list[str] = []
    for table, keys in sorted(after.items()):
        new_keys = keys - before.get(table, set())
        if not new_keys:
            continue
        shown = sorted(new_keys, key=repr)[:10]
        lines = [f"{table}: {len(new_keys)} row(s) added"]
        lines += [f"    {key!r}" for key in shown]
        if len(new_keys) > len(shown):
            lines.append(f"    … and {len(new_keys) - len(shown)} more")
        added.append("\n  ".join(lines))

    assert not added, (
        "the test run ADDED rows to seeded reference tables and left them "
        "there:\n  " + "\n  ".join(added) + "\n\nA seeded reference table is "
        "config, not scratch space — every row left behind is read by every "
        "later run. Take the row back with `owned_row` (tests/conftest.py), "
        "which soft-deletes in a `finally` so a failing assertion cannot skip "
        "the undo. This is the #29 defect: 48 leaked rows in "
        "core_compliance_deadlines made three suite runs fail three different "
        "ways, and no guard could see them."
    )


@asynccontextmanager
async def owned_row(session, row):
    """Add ``row`` for the body of a test, then take it back.

    **The R-9 lesson, applied to reference tables.** ``_backdated`` learned it
    for mutation: a docstring asking the caller to clean up is not an
    enforcement mechanism, a context manager is — there is no way to take the
    row without also taking the restore. ``seed_addition_guard`` is what makes
    forgetting this loud instead of silent.

    Undone by SOFT delete, which is both mandatory (the app role physically
    cannot hard-delete, rule 6) and sufficient: the unique indexes on these
    tables are partial on ``deleted_at IS NULL``, so the natural key is free
    again for the next run. That last part is not theoretical —
    ``core_holidays`` is exactly where a leaked row makes the SECOND run fail on
    a constraint violation.
    """
    from office_connect.core.soft_delete import soft_delete

    session.add(row)
    await session.commit()
    model, pk = type(row), row.id
    try:
        yield row
    finally:
        # Re-fetch by primary key rather than reusing ``row``. A test that
        # provokes an IntegrityError rolls its session back, and a rollback
        # expires every instance in it — touching ``row.deleted_at`` in this
        # synchronous ``finally`` would then emit lazy IO and raise
        # MissingGreenlet *instead of* undoing anything, which is the one
        # failure mode a cleanup path must not have.
        live = await session.get(model, pk)
        if live is not None:
            soft_delete(live)
            await session.commit()


@pytest.fixture(autouse=True)
async def _dispose_engine_pool():
    """asyncpg connections are event-loop-bound and pytest-asyncio gives each
    test its own loop — drain the shared pool after every test."""
    yield
    from office_connect.core import db

    await db.engine.dispose()


@pytest.fixture
async def client():
    """ASGI client with lifespan running (app.state.redis available)."""
    from office_connect.main import app

    async with LifespanManager(app) as manager:
        transport = ASGITransport(app=manager.app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


@pytest.fixture
async def app_session():
    """The real runtime path: oc_app role + OCSession listeners (audit chain,
    soft-delete filter, hard-delete guard)."""
    async with SessionLocal() as session:
        yield session


@pytest.fixture
async def owner_session():
    """Privileged path: oc_dev owner role, PLAIN session (no OCSession
    listeners) — for tamper attempts, privilege probes, and schema inspection."""
    engine = create_async_engine(
        get_settings().migration_database_url, poolclass=NullPool
    )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


# --- Auth fixtures (Stage B / Increment 2) --------------------------------


@pytest.fixture
async def session_redis():
    """A real client on the SESSION Redis DB (db 4). Flushed around each test —
    safe because db 4 holds only auth sessions/throttle/pending-MFA (never db 0)."""
    import redis.asyncio as aioredis

    r = aioredis.from_url(
        get_settings().resolved_session_redis_url, decode_responses=True
    )
    await r.flushdb()
    try:
        yield r
    finally:
        await r.flushdb()
        await r.aclose()


@pytest.fixture
async def session_store(session_redis):
    from office_connect.core.auth.session_store import SessionStore

    return SessionStore(session_redis, get_settings())


@pytest.fixture
async def permission_cache(session_redis):
    """The RBAC permission cache over the same db-4 keyspace the app uses (B3)."""
    from office_connect.core.auth.permission_cache import PermissionCache

    return PermissionCache(session_redis, get_settings())


@pytest.fixture
async def reimb_flag_on(app_session):
    """Flip ``module.reimbursement`` ON for the test, restoring the prior state
    after (the dev DB seeds it OFF in migration 0001 — fail-safe default)."""
    from office_connect.core.models import FeatureFlag

    row = (
        await app_session.execute(
            select(FeatureFlag).where(FeatureFlag.key == "module.reimbursement")
        )
    ).scalar_one_or_none()
    created = row is None
    prev_enabled = None if created else row.enabled
    prev_active = None if created else row.is_active
    if created:
        row = FeatureFlag(
            key="module.reimbursement", enabled=True, is_active=True,
            description="Local Travel Reimbursement module",
        )
        app_session.add(row)
    else:
        row.enabled = True
        row.is_active = True
    await app_session.commit()
    yield row
    if created:
        row.enabled = False  # no hard deletes — park it back OFF
    else:
        row.enabled = prev_enabled
        row.is_active = prev_active
    await app_session.commit()


@pytest.fixture
async def reimb_flag_off(app_session):
    """Force ``module.reimbursement`` OFF for the test, restoring the prior state
    after (the dev DB may have been flipped ON by a walkthrough).

    Promoted out of ``test_reimb_api_flag_gate.py`` at R-9 when the authorization
    census became its second consumer — the census probes all 28 gated routes
    flag-OFF, and a second copy of a fixture that RESTORES STATE is precisely the
    hygiene shape (c) that has now bitten this suite four times.
    """
    from office_connect.core.models import FeatureFlag

    row = (
        await app_session.execute(
            select(FeatureFlag).where(FeatureFlag.key == "module.reimbursement")
        )
    ).scalar_one_or_none()
    created = row is None
    prev = None if created else (row.enabled, row.is_active)
    if created:
        row = FeatureFlag(
            key="module.reimbursement",
            enabled=False,
            description="Local Travel Reimbursement module",
        )
        app_session.add(row)
    else:
        row.enabled = False
    await app_session.commit()
    yield row
    if not created:
        row.enabled, row.is_active = prev
        await app_session.commit()


@pytest.fixture
def no_scan_worker():
    """Unhook the attachment scan enqueuer so an uploaded row STAYS ``pending``.

    **Without this, asserting ``scan_status == "pending"`` is a race the test can
    only win by being quick.** An upload enqueues ``ops.scan_attachment`` after
    commit (``core/attachments/scan_queue.py``), the worker container is up during
    a suite run, and the NullScanner turns a row ``clean`` in well under a tenth
    of a second. Not hypothetical: at the Stage D gate run, attachment 3109 was
    inserted at 07:24:58.797, scanned at 07:24:58.874 — 77 ms later — and the
    assertion ran 36 ms after *that*. The same test then passed five times in a
    row in isolation, which is exactly how a race disguises itself as a fluke.

    The house save/replace/restore idiom, same as the capturing enqueuer in
    ``test_attachments_api.py`` and ``register_enqueuer(None)`` in
    ``test_reimb_packet_api.py``. Nothing is left permanently unscanned — the
    every-5-min beat sweeper still drains the row.
    """
    from office_connect.core.attachments import scan_queue

    previous = scan_queue._enqueuer
    scan_queue.register_enqueuer(None)
    try:
        yield
    finally:
        scan_queue._enqueuer = previous


@pytest.fixture
async def seed_rbac(app_session):
    """Idempotently seed the permission/role catalogs + default grants."""
    from office_connect.core.seeds import apply_dataset
    from office_connect.core.seeds.rbac import (
        PERMISSIONS_DATASET,
        ROLES_DATASET,
        apply_rbac_grants,
    )

    await apply_dataset(app_session, PERMISSIONS_DATASET)
    await apply_dataset(app_session, ROLES_DATASET)
    await apply_rbac_grants(app_session)
    await app_session.commit()


@pytest.fixture
async def make_user(app_session):
    """Factory: create a live ``core_users`` row (random email) with optional
    roles/MFA. Returns ``(user, plaintext_password)``. Roles are looked up by code
    (created if absent), so grant seeding is optional unless the test needs the
    role's permissions (request ``seed_rbac`` for those).

    ⚠ **A role minted here is a row in a SEEDED table.** ``core_roles`` is one of
    the 13 datasets ``seed_addition_guard`` watches, and its five rows are config.
    Today every caller happens to name one of those five, so nothing is minted and
    nothing leaks — the hazard is latent, which is the only reason it survived
    this long. The first ``roles=("some_new_thing",)`` would put a permanent role
    in the catalog from conftest itself, the least useful place for a defect to
    live. Undoing what this factory CREATED costs one list and one loop; the
    seeded five are looked up, never minted, and never touched.
    """
    from office_connect.core.models import Role, User, UserRole
    from office_connect.core.security import hash_password
    from office_connect.core.soft_delete import soft_delete

    minted: list[int] = []  # PKs, not instances — a rollback expires instances

    async def _make(
        *,
        password: str | None = DEFAULT_TEST_PASSWORD,
        email: str | None = None,
        roles: tuple[str, ...] = (),
        **kwargs,
    ):
        email = email or f"t-{secrets.token_hex(6)}@doh.gov"
        user = User(
            email=email,
            password_hash=hash_password(password) if password else None,
            is_active=True,
            **kwargs,
        )
        app_session.add(user)
        await app_session.flush()
        for code in roles:
            role = (
                await app_session.execute(select(Role).where(Role.code == code))
            ).scalar_one_or_none()
            if role is None:
                role = Role(code=code, name=code.replace("_", " ").title())
                app_session.add(role)
                await app_session.flush()
                minted.append(role.id)
            app_session.add(UserRole(user_id=user.id, role_id=role.id))
        await app_session.commit()
        await app_session.refresh(user)
        return user, password

    yield _make

    for role_id in minted:
        live = await app_session.get(Role, role_id)
        if live is not None:
            soft_delete(live)
    if minted:
        await app_session.commit()
