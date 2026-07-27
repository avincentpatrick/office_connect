"""Workflow SLA sweep task (Stage C — the shared workflow engine).

``core`` may not import the worker (import-linter), so the beat-scheduled SLA sweep
lives here and calls the pure ``core.workflow.sweep_due_steps`` via the async-in-worker
pattern (a fresh NullPool engine + ``OCSession`` audit context, disposed in ``finally``
— the same discipline as ``ops/attachments_tasks.py``). The sweep is idempotent and
non-interrupting; a cheap no-op when no step is overdue.

Notification delivery for escalations is deferred to R-4-app, which will register a
callable via ``core.workflow.register_sla_enqueuer`` — the ops→core seam mirrors the
attachments/notification enqueuers. None is wired here.
"""

from __future__ import annotations

import asyncio
from typing import Any

# Registering these installs the OCSession audit + soft-delete listeners.
import office_connect.core.audit  # noqa: F401
import office_connect.core.soft_delete  # noqa: F401
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from office_connect.core.config import get_settings
from office_connect.core.session import OCSession, set_audit_context
from office_connect.core.workflow import sweep_due_steps
from office_connect.worker import celery_app


async def _with_app_session(work) -> Any:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        sync_session_class=OCSession,
        expire_on_commit=False,
    )
    try:
        async with factory() as session:
            set_audit_context(session, request_id="workflow-sla")
            result = await work(session)
            await session.commit()
            return result
    finally:
        await engine.dispose()


@celery_app.task(name="ops.sweep_workflow_sla", bind=True, acks_late=True)
def sweep_workflow_sla(self, limit: int = 200) -> dict[str, Any]:
    return asyncio.run(_with_app_session(lambda s: sweep_due_steps(s, limit=limit)))
