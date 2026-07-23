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


@pytest.fixture(scope="session", autouse=True)
def migrated_db():
    """Upgrade to head once before the suite (idempotency is itself a test)."""
    result = subprocess.run(
        ["alembic", "upgrade", "head"], capture_output=True, text=True, cwd=REPO_ROOT
    )
    assert result.returncode == 0, result.stderr


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
