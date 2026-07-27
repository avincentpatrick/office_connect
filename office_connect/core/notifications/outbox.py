"""Outbox persistence + the enqueue injection seam.

``persist_notification`` writes a ``core_notifications`` row (with dedup) into the
caller's session — the transactional-outbox pattern, so the row commits atomically
with the business change. Enqueue happens strictly **after commit**: a global
``after_commit`` listener drains ids registered via ``dispatch_on_commit``, so a
task never runs before its row is visible and rolled-back work never enqueues.

``core`` may not import the worker (import-linter), so the actual enqueue is
injected: ``ops`` calls ``register_enqueuer`` at import.
"""

from __future__ import annotations

from typing import Any, Callable

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.config import Settings, get_settings
from office_connect.core.email import EmailMessage
from office_connect.core.models.notification import NotificationOutbox
from office_connect.core.notifications.recipients import resolve_recipient
from office_connect.core.session import OCSession

# The injected enqueue callable (ops registers a Celery send_task). None = no
# worker wired → callers fall back to inline dispatch.
_enqueuer: Callable[[int], None] | None = None
_PENDING_ENQUEUE_KEY = "pending_notification_enqueues"


def register_enqueuer(fn: Callable[[int], None]) -> None:
    """Install the enqueue callable (ops → core injection; keeps core pure)."""
    global _enqueuer
    _enqueuer = fn


def enqueue(notification_id: int) -> bool:
    """Enqueue a dispatch if a worker is wired. Returns True if enqueued."""
    if _enqueuer is None:
        return False
    _enqueuer(notification_id)
    return True


def _payload_from(notification) -> dict[str, Any]:
    email = notification.email
    if notification.channel == "email" and email is not None:
        return {
            "to": list(email.to),
            "cc": list(email.cc),
            "html_body": email.html_body,
            "sender": email.sender,
        }
    return {}


async def persist_notification(
    session: AsyncSession, notification, *, settings: Settings | None = None
) -> int:
    """Persist an outbox row (idempotent on ``meta['dedup_key']``); return its id.

    Adds to the caller's session and flushes — does NOT commit (the caller owns
    the unit of work)."""
    settings = settings or get_settings()
    meta = notification.meta or {}
    dedup_key = meta.get("dedup_key")
    if dedup_key:
        existing = (
            await session.execute(
                select(NotificationOutbox.id).where(
                    NotificationOutbox.dedup_key == dedup_key,
                    NotificationOutbox.status != "dead",
                )
            )
        ).scalars().first()
        if existing is not None:
            return existing

    email = notification.email
    # Resolve the concrete recipient (user_id → email) and honor delivery prefs —
    # a suppressed (opted-out / unresolvable) row is persisted but never dispatched.
    resolved = await resolve_recipient(session, notification, settings=settings)
    row = NotificationOutbox(
        channel=notification.channel,
        status=resolved.status,
        recipient_email=resolved.recipient_email,
        recipient_user_id=resolved.recipient_user_id,
        subject=(email.subject if email else meta.get("subject", "")),
        body_text=(email.text_body if email else meta.get("body_text")),
        payload=_payload_from(notification),
        meta=meta,
        dedup_key=dedup_key,
        module=meta.get("module"),
        activity_id=meta.get("activity_id"),
        max_attempts=settings.notifications_max_attempts,
    )
    session.add(row)
    await session.flush()
    return row.id


def dispatch_on_commit(session: AsyncSession, notification_id: int) -> None:
    """Register ``notification_id`` to be enqueued after this session commits."""
    sync_session = session.sync_session if isinstance(session, AsyncSession) else session
    sync_session.info.setdefault(_PENDING_ENQUEUE_KEY, []).append(notification_id)


@event.listens_for(OCSession, "after_commit")
def _drain_pending_enqueues(session) -> None:
    """After a successful commit, enqueue any ids registered this transaction.
    Fires only on commit (never rollback) and after the rows are visible."""
    ids = session.info.pop(_PENDING_ENQUEUE_KEY, None)
    if not ids:
        return
    for notification_id in ids:
        enqueue(notification_id)


def message_from_row(row: NotificationOutbox) -> EmailMessage:
    """Rebuild the transport ``EmailMessage`` from a persisted outbox row."""
    payload = row.payload or {}
    to = payload.get("to") or ([row.recipient_email] if row.recipient_email else [])
    return EmailMessage(
        to=list(to),
        subject=row.subject,
        text_body=row.body_text or "",
        html_body=payload.get("html_body"),
        sender=payload.get("sender"),
        cc=list(payload.get("cc") or []),
    )
