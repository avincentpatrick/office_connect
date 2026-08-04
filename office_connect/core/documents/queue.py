"""Per-subject generation-enqueue seam (core-service #8, Stage C R-5).

An exact clone of ``core/attachments/scan_queue.py``, which is itself the
notifications enqueuer's shape: a caller registers a subject to be rendered
**after its row commits**, so the worker never starts before the claim's data is
visible and a rolled-back save never enqueues a render of numbers that no longer
exist. ``core`` may not import the worker (import-linter), so ``ops`` injects the
real Celery ``send_task`` via ``register_enqueuer`` at import time.

Two shape differences from the scan queue, both deliberate:

- The payload is ``(subject_kind, subject_id)``, not a bare id. Generation is
  polymorphic across modules from day one (reimb now; dtwis/qms/perf later), and
  core must not own a table of "things that can be rendered".
- There is **no beat sweeper fallback**. A missed scan self-heals because
  ``scan_status='pending'`` is a durable to-do marker; a missed render leaves no
  such marker, because the checklist item simply stays un-generated. ``enqueue``
  returning ``False`` is therefore surfaced to the user as a non-blocking notice
  (spec §19.12) rather than silently retried — and the caller can always ask
  again. This is why the generate endpoint is idempotent.
"""

from __future__ import annotations

from typing import Callable

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.session import OCSession

# Injected enqueue callable (ops registers a Celery send_task). None = no worker
# wired → enqueue() reports False and the caller degrades non-blockingly.
_enqueuer: Callable[[str, int], None] | None = None
# Distinct from the notifications and scan keys so the after_commit drains
# never clash.
_PENDING_RENDER_KEY = "pending_document_renders"


def register_enqueuer(fn: Callable[[str, int], None] | None) -> None:
    """Install the enqueue callable (ops → core injection; keeps core pure)."""
    global _enqueuer
    _enqueuer = fn


def is_wired() -> bool:
    """Whether a worker is registered.

    Lets a request handler tell the user "queued" from "nobody is listening"
    *before* it commits, which is the difference between an honest non-blocking
    notice and a spinner that never resolves (spec §19.12).
    """
    return _enqueuer is not None


def enqueue(subject_kind: str, subject_id: int) -> bool:
    """Enqueue a render if a worker is wired. Returns True if enqueued."""
    if _enqueuer is None:
        return False
    _enqueuer(subject_kind, subject_id)
    return True


def generate_on_commit(
    session: AsyncSession, subject_kind: str, subject_id: int
) -> None:
    """Register a subject to be rendered after this session commits.

    Deduplicates within the transaction: submitting a claim recomputes totals,
    materializes the checklist and starts a workflow instance, and more than one
    of those paths may ask for the packet. One commit should enqueue one render.
    """
    sync_session = session.sync_session if isinstance(session, AsyncSession) else session
    pending = sync_session.info.setdefault(_PENDING_RENDER_KEY, [])
    subject = (subject_kind, subject_id)
    if subject not in pending:
        pending.append(subject)


@event.listens_for(OCSession, "after_commit")
def _drain_pending_renders(session) -> None:
    """Enqueue the subjects registered this transaction, after a successful commit."""
    subjects = session.info.pop(_PENDING_RENDER_KEY, None)
    if not subjects:
        return
    for subject_kind, subject_id in subjects:
        enqueue(subject_kind, subject_id)
