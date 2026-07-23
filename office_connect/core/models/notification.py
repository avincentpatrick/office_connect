"""Notification outbox + in-app center + delivery log (core-service #4).

Master-plan §1.1 #4. One notifications service: modules emit events, this owns
delivery. Two tables:
- ``core_notifications`` (business, mutable) — the outbox AND the in-app center,
  distinguished by ``channel``. Status flows queued→sending→sent/failed→dead.
  ``read_at`` is the in-app read receipt; ``recipient_user_id`` is the future FK
  the Stage-B/D bell keys on (no ``core_users`` yet).
- ``core_notification_deliveries`` (append-only) — one row per delivery attempt;
  the dead-letter / failed-jobs observability substrate. REVOKE UPDATE + unaudited
  (it IS a log, like ``core_query_logs``).
"""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Enum, ForeignKey, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from office_connect.core.base import (
    AuditColsMixin,
    Base,
    PKMixin,
    SoftDeleteMixin,
)

NotificationChannel = Enum("email", "in_app", name="core_notification_channel")
NotificationStatus = Enum(
    "queued", "sending", "sent", "failed", "dead", name="core_notification_status"
)
DeliveryOutcome = Enum(
    "sent", "failed", name="core_notification_delivery_outcome"
)


class NotificationOutbox(PKMixin, AuditColsMixin, SoftDeleteMixin, Base):
    __tablename__ = "core_notifications"
    __table_args__ = (
        Index("ix_core_notifications_status", "status"),
        Index("ix_core_notifications_channel", "channel"),
        Index("ix_core_notifications_recipient_user_id", "recipient_user_id"),
        Index("ix_core_notifications_recipient_email", "recipient_email"),
        Index("ix_core_notifications_module", "module"),
        Index("ix_core_notifications_scheduled_at", "scheduled_at"),
        Index("ix_core_notifications_activity_id", "activity_id"),
        # Idempotency: at most one live, non-dead notification per dedup key.
        Index(
            "uq_core_notifications_dedup_key",
            "dedup_key",
            unique=True,
            postgresql_where=text(
                "dedup_key IS NOT NULL AND deleted_at IS NULL AND status <> 'dead'"
            ),
        ),
        # Unread-bell badge count (Stage D).
        Index(
            "ix_core_notifications_unread",
            "recipient_user_id",
            postgresql_where=text(
                "channel = 'in_app' AND read_at IS NULL AND deleted_at IS NULL"
            ),
        ),
    )

    channel: Mapped[str] = mapped_column(NotificationChannel)
    status: Mapped[str] = mapped_column(NotificationStatus, server_default="queued")
    recipient_email: Mapped[str | None]
    recipient_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("core_users.id")
    )
    subject: Mapped[str]
    body_text: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb")
    )
    meta: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb")
    )
    dedup_key: Mapped[str | None]
    module: Mapped[str | None]
    activity_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("core_activities.id")
    )
    attempt_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    max_attempts: Mapped[int] = mapped_column(Integer, server_default=text("5"))
    last_error: Mapped[str | None] = mapped_column(Text)
    scheduled_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    sent_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    driver: Mapped[str | None]
    dispatched_message_id: Mapped[str | None]
    read_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class NotificationDelivery(PKMixin, Base):
    """Append-only delivery-attempt log: created_at only, REVOKE UPDATE, unaudited."""

    __tablename__ = "core_notification_deliveries"
    __table_args__ = (
        Index("ix_core_notification_deliveries_notification_id", "notification_id"),
        Index("ix_core_notification_deliveries_outcome", "outcome"),
        Index("ix_core_notification_deliveries_created_at", "created_at"),
    )

    notification_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("core_notifications.id")
    )
    attempt_no: Mapped[int] = mapped_column(Integer)
    outcome: Mapped[str] = mapped_column(DeliveryOutcome)
    driver: Mapped[str | None]
    message_id: Mapped[str | None]
    error: Mapped[str | None] = mapped_column(Text)
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("core_users.id")
    )
