"""Per-upload scan-enqueue seam (Stage B / Increment 4).

Mirrors the notifications enqueuer (``core/notifications/outbox.py``): the
attachments HTTP router registers an attachment id to be scanned **after its row
commits**, so the worker never runs before the row is visible and a rolled-back
upload never enqueues. ``core`` may not import the worker (import-linter), so
``ops`` injects the real Celery ``send_task`` via ``register_enqueuer`` at import.

If no worker/broker is wired, ``enqueue`` returns ``False`` and the every-5-min
beat sweeper (``ops.scan_pending_attachments``) still drains the ``pending`` row —
the same safety net as before the router existed.
"""

from __future__ import annotations

from typing import Callable

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.session import OCSession

# Injected enqueue callable (ops registers a Celery send_task). None = no worker
# wired → the beat sweeper is the fallback.
_enqueuer: Callable[[int], None] | None = None
# Distinct from the notifications key so the two after_commit drains never clash.
_PENDING_SCAN_KEY = "pending_attachment_scans"


def register_enqueuer(fn: Callable[[int], None]) -> None:
    """Install the enqueue callable (ops → core injection; keeps core pure)."""
    global _enqueuer
    _enqueuer = fn


def enqueue(attachment_id: int) -> bool:
    """Enqueue a scan if a worker is wired. Returns True if enqueued."""
    if _enqueuer is None:
        return False
    _enqueuer(attachment_id)
    return True


def scan_on_commit(session: AsyncSession, attachment_id: int) -> None:
    """Register ``attachment_id`` to be enqueued after this session commits."""
    sync_session = session.sync_session if isinstance(session, AsyncSession) else session
    sync_session.info.setdefault(_PENDING_SCAN_KEY, []).append(attachment_id)


@event.listens_for(OCSession, "after_commit")
def _drain_pending_scans(session) -> None:
    """Enqueue the ids registered this transaction, after a successful commit."""
    ids = session.info.pop(_PENDING_SCAN_KEY, None)
    if not ids:
        return
    for attachment_id in ids:
        enqueue(attachment_id)
