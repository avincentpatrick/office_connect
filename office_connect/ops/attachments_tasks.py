"""Attachment scan tasks (Increment 4).

The scan + re-encode step runs in the worker, not the request path — ClamAV needs
warm-up/RAM and image decode blocks the loop. ``core`` may not import the worker
(import-linter), so the Celery task lives here and calls the pure
``core.attachments.process_attachment`` via the async-in-worker pattern (a fresh
NullPool engine + ``OCSession`` audit context, disposed in ``finally`` — the same
discipline as ``ops/restore_drill.py`` and ``ops/bootstrap.py``).

- ``ops.scan_attachment(id)`` — scan one attachment (retries on transient error).
- ``ops.scan_pending_attachments()`` — a beat sweeper that drains pending/error
  rows. Until the Stage-B upload router enqueues per-upload, this is how uploads
  get scanned; scheduled in ``worker.py``.
"""

from __future__ import annotations

import asyncio
from typing import Any

# Registering these installs the OCSession audit + soft-delete listeners.
import office_connect.core.audit  # noqa: F401
import office_connect.core.soft_delete  # noqa: F401
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from office_connect.core.attachments.scan_queue import register_enqueuer
from office_connect.core.attachments.service import process_attachment
from office_connect.core.config import get_settings
from office_connect.core.models import Attachment
from office_connect.core.session import OCSession, set_audit_context
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
            set_audit_context(session, request_id="attachment-scan")
            result = await work(session)
            await session.commit()
            return result
    finally:
        await engine.dispose()


async def _scan_one(session: AsyncSession, attachment_id: int) -> str:
    return await process_attachment(session, attachment_id)


async def _scan_pending(session: AsyncSession, limit: int) -> dict[str, Any]:
    ids = list(
        (
            await session.execute(
                select(Attachment.id)
                .where(Attachment.scan_status.in_(("pending", "error")))
                .order_by(Attachment.id)
                .limit(limit)
            )
        ).scalars()
    )
    results: dict[int, str] = {}
    for attachment_id in ids:
        results[attachment_id] = await process_attachment(session, attachment_id)
    return {"scanned": len(ids), "results": results}


@celery_app.task(
    name="ops.scan_attachment",
    bind=True,
    acks_late=True,
    max_retries=3,
    default_retry_delay=60,
)
def scan_attachment(self, attachment_id: int) -> dict[str, Any]:
    status = asyncio.run(_with_app_session(lambda s: _scan_one(s, attachment_id)))
    # A transient 'error' verdict (scanner outage) is worth retrying; a terminal
    # 'infected'/'clean' is not.
    if status == "error" and self.request.retries < self.max_retries:
        raise self.retry(countdown=60 * (self.request.retries + 1))
    return {"attachment_id": attachment_id, "scan_status": status}


@celery_app.task(name="ops.scan_pending_attachments", bind=True, acks_late=True)
def scan_pending_attachments(self, limit: int = 100) -> dict[str, Any]:
    return asyncio.run(_with_app_session(lambda s: _scan_pending(s, limit)))


# ops → core injection (import-linter-legal): the upload router enqueues a
# per-upload scan after commit via this callable. Mirrors notification_tasks.py.
register_enqueuer(
    lambda attachment_id: celery_app.send_task(
        "ops.scan_attachment", args=[attachment_id]
    )
)
