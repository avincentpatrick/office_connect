"""Outbox dispatch primitive — the callable the Celery task wraps.

``dispatch_outbox_row(id)`` opens its own audited session, claims the row
(queued/failed→sending with a ``skip_locked`` row lock so two workers never
double-send), calls the email transport, and records the outcome + an append-only
delivery row — all in one transaction. It **raises** on transport failure so the
Celery task can retry; ``mark_dead`` moves a row to the terminal dead-letter state
after retries are exhausted.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.config import Settings, get_settings
from office_connect.core.email import EmailError, SendResult, get_email_driver
from office_connect.core.models.notification import (
    NotificationDelivery,
    NotificationOutbox,
)
from office_connect.core.notifications.outbox import message_from_row
from office_connect.core.session import app_session_scope
from office_connect.core.time import utc_now


def _add_delivery(
    session: AsyncSession,
    row: NotificationOutbox,
    *,
    outcome: str,
    driver: str | None = None,
    message_id: str | None = None,
    error: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    session.add(
        NotificationDelivery(
            notification_id=row.id,
            attempt_no=row.attempt_count,
            outcome=outcome,
            driver=driver,
            message_id=message_id,
            error=error,
            detail=detail,
        )
    )


async def dispatch_outbox_row(
    notification_id: int, *, settings: Settings | None = None
) -> SendResult:
    """Dispatch one outbox row. Raises ``EmailError`` on transport failure."""
    settings = settings or get_settings()
    async with app_session_scope(
        settings, request_id=f"notify:{notification_id}"
    ) as session:
        row = (
            await session.execute(
                select(NotificationOutbox)
                .where(NotificationOutbox.id == notification_id)
                .with_for_update(skip_locked=True)
            )
        ).scalar_one_or_none()
        if row is None:  # absent or locked by another worker → nothing to do
            return SendResult(driver="none", sent=False, recipients=[])
        if row.status == "sent":  # idempotent: acks_late redelivery won't re-send
            return SendResult(
                driver=row.driver or "none",
                sent=True,
                recipients=[row.recipient_email] if row.recipient_email else [],
                message_id=row.dispatched_message_id,
            )
        if row.status == "suppressed":  # opt-out honored at persist time — never send
            return SendResult(
                driver="suppressed",
                sent=False,
                recipients=[row.recipient_email] if row.recipient_email else [],
            )

        row.status = "sending"
        row.attempt_count += 1

        if row.channel == "in_app":  # the row IS the delivery (Stage D adds pub/sub)
            row.status = "sent"
            row.sent_at = utc_now()
            row.driver = "in_app"
            _add_delivery(session, row, outcome="sent", driver="in_app")
            await session.commit()
            return SendResult(
                driver="in_app",
                sent=True,
                recipients=[row.recipient_email] if row.recipient_email else [],
            )

        message = message_from_row(row)
        try:
            result = get_email_driver(settings).send(message)
        except EmailError as exc:
            row.status = "failed"
            row.last_error = str(exc)[:2000]
            _add_delivery(session, row, outcome="failed", error=str(exc))
            await session.commit()
            raise

        row.status = "sent"
        row.sent_at = utc_now()
        row.driver = result.driver
        row.dispatched_message_id = result.message_id
        _add_delivery(
            session,
            row,
            outcome="sent",
            driver=result.driver,
            message_id=result.message_id,
            detail={"recipients": result.recipients},
        )
        await session.commit()
        return result


async def mark_dead(
    notification_id: int, error: str, *, settings: Settings | None = None
) -> None:
    """Terminal dead-letter state after retries are exhausted."""
    settings = settings or get_settings()
    async with app_session_scope(
        settings, request_id=f"notify-dead:{notification_id}"
    ) as session:
        row = (
            await session.execute(
                select(NotificationOutbox).where(
                    NotificationOutbox.id == notification_id
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return
        row.status = "dead"
        row.last_error = error[:2000]
        _add_delivery(session, row, outcome="failed", error=error)
        await session.commit()
