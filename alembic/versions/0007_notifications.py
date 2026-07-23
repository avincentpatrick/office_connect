"""notifications — durable outbox + in-app center + append-only delivery log

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-23

Increment 4 (spine amendments), master-plan §1.1 #4.
- core_notifications: business (mutable) — oc_app inherits SELECT/INSERT/UPDATE.
- core_notification_deliveries: append-only — created_* only; MUST REVOKE UPDATE
  from oc_app (default privileges from 0001 grant it to future tables).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _audit_soft_delete_cols() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("updated_by", sa.BigInteger(), nullable=True),
        sa.Column("deleted_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.BigInteger(), nullable=True),
    ]


def upgrade() -> None:
    channel = postgresql.ENUM("email", "in_app", name="core_notification_channel")
    channel.create(op.get_bind(), checkfirst=True)
    status = postgresql.ENUM(
        "queued", "sending", "sent", "failed", "dead", name="core_notification_status"
    )
    status.create(op.get_bind(), checkfirst=True)
    outcome = postgresql.ENUM(
        "sent", "failed", name="core_notification_delivery_outcome"
    )
    outcome.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "core_notifications",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column(
            "channel",
            postgresql.ENUM(name="core_notification_channel", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(name="core_notification_status", create_type=False),
            server_default="queued",
            nullable=False,
        ),
        sa.Column("recipient_email", sa.String(), nullable=True),
        sa.Column("recipient_user_id", sa.BigInteger(), nullable=True),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "meta",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("dedup_key", sa.String(), nullable=True),
        sa.Column("module", sa.String(), nullable=True),
        sa.Column("activity_id", sa.BigInteger(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default=sa.text("5"), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "scheduled_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("sent_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("driver", sa.String(), nullable=True),
        sa.Column("dispatched_message_id", sa.String(), nullable=True),
        sa.Column("read_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        *_audit_soft_delete_cols(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_core_notifications")),
        sa.ForeignKeyConstraint(
            ["activity_id"],
            ["core_activities.id"],
            name=op.f("fk_core_notifications_activity_id_core_activities"),
        ),
    )
    op.create_index("ix_core_notifications_status", "core_notifications", ["status"])
    op.create_index("ix_core_notifications_channel", "core_notifications", ["channel"])
    op.create_index(
        "ix_core_notifications_recipient_user_id",
        "core_notifications",
        ["recipient_user_id"],
    )
    op.create_index(
        "ix_core_notifications_recipient_email",
        "core_notifications",
        ["recipient_email"],
    )
    op.create_index("ix_core_notifications_module", "core_notifications", ["module"])
    op.create_index(
        "ix_core_notifications_scheduled_at", "core_notifications", ["scheduled_at"]
    )
    op.create_index(
        "ix_core_notifications_activity_id", "core_notifications", ["activity_id"]
    )
    op.create_index(
        "uq_core_notifications_dedup_key",
        "core_notifications",
        ["dedup_key"],
        unique=True,
        postgresql_where=sa.text(
            "dedup_key IS NOT NULL AND deleted_at IS NULL AND status <> 'dead'"
        ),
    )
    op.create_index(
        "ix_core_notifications_unread",
        "core_notifications",
        ["recipient_user_id"],
        postgresql_where=sa.text(
            "channel = 'in_app' AND read_at IS NULL AND deleted_at IS NULL"
        ),
    )

    op.create_table(
        "core_notification_deliveries",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("notification_id", sa.BigInteger(), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column(
            "outcome",
            postgresql.ENUM(
                name="core_notification_delivery_outcome", create_type=False
            ),
            nullable=False,
        ),
        sa.Column("driver", sa.String(), nullable=True),
        sa.Column("message_id", sa.String(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("detail", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_core_notification_deliveries")),
        sa.ForeignKeyConstraint(
            ["notification_id"],
            ["core_notifications.id"],
            name=op.f(
                "fk_core_notification_deliveries_notification_id_core_notifications"
            ),
        ),
    )
    op.create_index(
        "ix_core_notification_deliveries_notification_id",
        "core_notification_deliveries",
        ["notification_id"],
    )
    op.create_index(
        "ix_core_notification_deliveries_outcome",
        "core_notification_deliveries",
        ["outcome"],
    )
    op.create_index(
        "ix_core_notification_deliveries_created_at",
        "core_notification_deliveries",
        ["created_at"],
    )
    # Append-only: default privileges granted UPDATE to future tables — revoke it.
    op.execute("REVOKE UPDATE ON core_notification_deliveries FROM oc_app")


def downgrade() -> None:
    op.drop_table("core_notification_deliveries")
    op.drop_table("core_notifications")
    postgresql.ENUM(name="core_notification_delivery_outcome").drop(
        op.get_bind(), checkfirst=True
    )
    postgresql.ENUM(name="core_notification_status").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="core_notification_channel").drop(op.get_bind(), checkfirst=True)
