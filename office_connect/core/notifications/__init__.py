"""Notification outbox — core-service #4 seam (STUB).

Rule 10 (shared service first): every module emits notification *events* here;
one core service owns delivery. This increment ships the **seam and the email
transport only**. The durable pieces — the ``core_notifications`` outbox table,
Celery retry/back-off, the in-app bell + notification center, per-user prefs —
land in **Increment 4** (master-plan §1.1 row 4). The research pattern is an
after-commit dispatch (``core/events.py``) that later writes an outbox row
consumed by a beat task; the *caller-facing* signatures below do not change when
that lands — a module still calls ``send_notification`` / emits an event.

For now ``send_notification`` dispatches synchronously through the configured
email driver (``log`` in dev, so no SMTP server is needed to exercise the path).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from office_connect.core.config import Settings, get_settings
from office_connect.core.email import EmailError, EmailMessage, SendResult, get_email_driver

__all__ = [
    "Notification",
    "send_notification",
    "send_test_email",
]


@dataclass
class Notification:
    """A single notification event. ``channel`` selects the transport; only
    ``email`` exists this increment. ``meta`` carries free-form context that the
    Increment-4 outbox will persist (module, activity_id, dedup key, …)."""

    channel: str
    email: EmailMessage | None = None
    meta: dict[str, Any] = field(default_factory=dict)


def send_notification(
    notification: Notification, *, settings: Settings | None = None
) -> SendResult:
    """Dispatch one notification through the configured transport.

    STUB behaviour: synchronous send. Increment 4 replaces the body with
    persist-to-outbox + after-commit dispatch without changing this signature.
    """
    settings = settings or get_settings()
    if notification.channel == "email":
        if notification.email is None:
            raise EmailError("email notification has no message")
        return get_email_driver(settings).send(notification.email)
    raise ValueError(f"unknown notification channel {notification.channel!r}")


def send_test_email(to: str, *, settings: Settings | None = None) -> dict[str, Any]:
    """Send a diagnostic test email through the selected driver (or log in dev).

    The Increment-3 test-email path: proves the notification seam + email driver
    are wired. Returns a JSON-serializable summary for the bootstrap CLI.
    """
    settings = settings or get_settings()
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
