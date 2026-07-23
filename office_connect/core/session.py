"""Dedicated sync Session subclass the platform listeners attach to.

``core/audit.py`` and ``core/soft_delete.py`` register their event listeners
against ``OCSession`` (not the global ``Session`` class), so Alembic and ad-hoc
scripts using plain sessions are unaffected. ``core/db.py`` wires it into the
async sessionmaker via ``sync_session_class`` and imports both listener modules
for their registration side effects.
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session


class OCSession(Session):
    """Sync session under every app ``AsyncSession`` — carries audit context."""


def set_audit_context(
    session: AsyncSession | Session,
    *,
    actor_id: int | None = None,
    request_id: str | None = None,
) -> None:
    """Record who/what is acting; the audit listeners read it at flush time."""
    sync_session = session.sync_session if isinstance(session, AsyncSession) else session
    if actor_id is not None:
        sync_session.info["actor_id"] = actor_id
    if request_id is not None:
        sync_session.info["request_id"] = request_id


@asynccontextmanager
async def app_session_scope(
    settings, *, request_id: str = "core", actor_id: int | None = None
) -> AsyncIterator[AsyncSession]:
    """An audited ``oc_app`` session on a fresh NullPool engine, disposed after.

    The standalone/worker pattern (matches ``ops/bootstrap.py::_with_app_session``)
    for core services that must open their own session outside a request — e.g.
    the notification outbox dispatcher. Imports the audit + soft-delete listeners
    so the writes are hash-chained even when ``core.db`` was never imported (a
    one-shot CLI or a Celery worker)."""
    # Lazy (avoids an import cycle: audit.py imports this module).
    import office_connect.core.audit  # noqa: F401
    import office_connect.core.soft_delete  # noqa: F401
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        sync_session_class=OCSession,
        expire_on_commit=False,
    )
    try:
        async with factory() as session:
            set_audit_context(session, actor_id=actor_id, request_id=request_id)
            yield session
    finally:
        await engine.dispose()
