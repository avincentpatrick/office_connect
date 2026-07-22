"""Dedicated sync Session subclass the platform listeners attach to.

``core/audit.py`` and ``core/soft_delete.py`` register their event listeners
against ``OCSession`` (not the global ``Session`` class), so Alembic and ad-hoc
scripts using plain sessions are unaffected. ``core/db.py`` wires it into the
async sessionmaker via ``sync_session_class`` and imports both listener modules
for their registration side effects.
"""

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
