"""Async SQLAlchemy engine + session factory.

Pool sized per plan §17.1 (size 10 / overflow 20). This is the single DB
choke-point CSS-IS's storage.py is migrated onto in Phase 1.

Connects as the runtime role ``oc_app`` (no DELETE anywhere). Alembic uses
``MIGRATION_DATABASE_URL`` (owner role ``oc_dev``) instead — see
``alembic/env.py``.
"""

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from office_connect.core.config import get_settings
from office_connect.core.session import OCSession, set_audit_context

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)

SessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, sync_session_class=OCSession, expire_on_commit=False
)

# Listener registration side effects: the audit chain and soft-delete filter
# attach to OCSession when these modules import. Keep these imports below the
# sessionmaker so every session produced by SessionLocal is covered.
from office_connect.core import audit as _audit  # noqa: E402,F401
from office_connect.core import soft_delete as _soft_delete  # noqa: E402,F401


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request, audit context pre-seeded
    with the request id (the actor is added by auth in Phase 2)."""
    async with SessionLocal() as session:
        set_audit_context(
            session, request_id=getattr(request.state, "request_id", None)
        )
        yield session
