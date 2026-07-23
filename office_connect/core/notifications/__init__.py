"""Notification outbox — core-service #4 (Increment 4).

Rule 10: modules emit notification *events*; one core service owns delivery.
``send_notification`` now **persists an outbox row and dispatches** (inline by
default; enqueued to the worker in ``celery`` mode) — the caller-facing signatures
are unchanged from the Increment-3 stub, so every existing caller keeps working.

Two entry points:
- ``send_notification`` / ``send_test_email`` — the standalone sync seam (CLI,
  tests, simple callers, no running event loop). Persists, commits, dispatches.
- ``persist_notification`` + ``dispatch_on_commit`` — the transactional path for
  async module handlers (Stage D): the outbox row commits atomically with the
  business change and the dispatch is enqueued after commit.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from office_connect.core.config import Settings, get_settings
from office_connect.core.email import EmailError, EmailMessage, SendResult
from office_connect.core.notifications.dispatch import dispatch_outbox_row, mark_dead
from office_connect.core.notifications.outbox import (
    dispatch_on_commit,
    enqueue,
    persist_notification,
    register_enqueuer,
)
from office_connect.core.session import app_session_scope

__all__ = [
    "Notification",
    "send_notification",
    "send_test_email",
    "persist_notification",
    "dispatch_on_commit",
    "dispatch_outbox_row",
    "mark_dead",
    "register_enqueuer",
]

_CHANNELS = ("email", "in_app")


@dataclass
class Notification:
    """A single notification event. ``channel`` selects the transport; ``meta``
    carries outbox context (module, activity_id, dedup_key, recipient_user_id, …)."""

    channel: str
    email: EmailMessage | None = None
    meta: dict[str, Any] = field(default_factory=dict)


def _validate(notification: Notification) -> None:
    if notification.channel not in _CHANNELS:
        raise ValueError(f"unknown notification channel {notification.channel!r}")
    if notification.channel == "email" and notification.email is None:
        raise EmailError("email notification has no message")


async def _send_standalone(
    notification: Notification, settings: Settings
) -> SendResult:
    async with app_session_scope(settings, request_id="notify") as session:
        notification_id = await persist_notification(
            session, notification, settings=settings
        )
        await session.commit()  # durable before any dispatch/enqueue

    if settings.notifications_dispatch == "celery" and enqueue(notification_id):
        recipients = notification.email.recipients if notification.email else []
        return SendResult(driver="queued", sent=False, recipients=recipients)
    return await dispatch_outbox_row(notification_id, settings=settings)


def send_notification(
    notification: Notification, *, settings: Settings | None = None
) -> SendResult:
    """Persist + dispatch one notification. Signature unchanged from Increment 3.

    Validates first (no DB touch on a bad call), then runs the standalone path.
    Must be called from a sync context (no running event loop)."""
    settings = settings or get_settings()
    _validate(notification)
    return asyncio.run(_send_standalone(notification, settings))


def send_test_email(to: str, *, settings: Settings | None = None) -> dict[str, Any]:
    """Send a diagnostic test email through the outbox. Returns the same JSON
    summary the bootstrap CLI has always printed.

    Forces **inline** dispatch even when the app runs in celery mode: a
    diagnostic must send now and report the real transport result, not 'queued'.
    """
    settings = settings or get_settings()
    settings = settings.model_copy(update={"notifications_dispatch": "inline"})
    message = EmailMessage(
        to=to,
        subject="Office-Connect test email",
        text_body=(
            "This is a test email from Office-Connect confirming the notification "
            "outbox and the selected email driver are wired correctly.\n"
        ),
    )
    result = send_notification(
        Notification(channel="email", email=message, meta={"kind": "test"}),
        settings=settings,
    )
    return {
        "driver": result.driver,
        "sent": result.sent,
        "recipients": result.recipients,
        "message_id": result.message_id,
    }
