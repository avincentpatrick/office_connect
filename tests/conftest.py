"""Phase-0 QA-gate fixtures.

Canonical invocation (docs/modules/foundation.md §6):

    docker compose exec app pytest -q

Tests run against the compose Postgres/Redis. The suite leaves benign test
rows behind in the dev DB (never tampered data — tamper tests roll back);
``docker compose down -v`` resets everything.
"""

import subprocess
from pathlib import Path

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
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
