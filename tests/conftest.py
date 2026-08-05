"""Phase-0 QA-gate fixtures.

Canonical invocation (docs/modules/foundation.md §6):

    docker compose exec app pytest -q

Tests run against the compose Postgres/Redis. The suite leaves benign test
rows behind in the dev DB (never tampered data — tamper tests roll back);
``docker compose down -v`` resets everything.
"""

import secrets
import subprocess
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

    **Scope: the rows the datasets DECLARE, and only those.** Tests create their
    own holidays, PAP codes and activity tags in the very same tables, with
    randomized keys — that is ordinary test data, not seed drift, and an earlier
    version of this guard that watched whole tables reported fifteen of them and
    said nothing useful. Narrowing it to the declared natural keys is what makes
    a failure here mean exactly one thing.

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
def make_user(app_session):
    """Factory: create a live ``core_users`` row (random email) with optional
    roles/MFA. Returns ``(user, plaintext_password)``. Roles are looked up by code
    (created if absent), so grant seeding is optional unless the test needs the
    role's permissions (request ``seed_rbac`` for those)."""
    from office_connect.core.models import Role, User, UserRole
    from office_connect.core.security import hash_password

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
            app_session.add(UserRole(user_id=user.id, role_id=role.id))
        await app_session.commit()
        await app_session.refresh(user)
        return user, password

    return _make
