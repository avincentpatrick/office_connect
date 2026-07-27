"""notification preferences + suppressed status

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-27

Stage B (Phase 2) Increment 4 — the one B4 migration (workstreams 1/3/4/5 are
app-layer). Adds:
- ``core_notification_preferences``: per-user × channel × optional-module opt-out
  (business/mutable — oc_app inherits SELECT/INSERT/UPDATE; NOT append-only, so no
  REVOKE UPDATE). Uniqueness uses NULLS NOT DISTINCT (PG16) so the module=NULL
  default row is unique per (user, channel) too.
- the ``suppressed`` value on ``core_notification_status`` — an opted-out outbox
  row is persisted (auditable) but never dispatched.

Downgrade drops the table but leaves the enum value in place: Postgres cannot DROP
an enum value, and nothing references it once the table is gone. Dev-only-downgrade
limitation, consistent with 0010's ORM-drift note.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: Union[str, None] = "0010"
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
    # New enum value first. PG16 allows ADD VALUE inside a transaction as long as
    # the value is not USED in the same transaction (it isn't here).
    op.execute(
        "ALTER TYPE core_notification_status ADD VALUE IF NOT EXISTS 'suppressed'"
    )

    op.create_table(
        "core_notification_preferences",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "channel",
            postgresql.ENUM(name="core_notification_channel", create_type=False),
            nullable=False,
        ),
        sa.Column("module", sa.String(), nullable=True),
        sa.Column(
            "enabled", sa.Boolean(), server_default=sa.true(), nullable=False
        ),
        *_audit_soft_delete_cols(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_core_notification_preferences")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["core_users.id"],
            name=op.f("fk_core_notification_preferences_user_id_core_users"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["core_users.id"],
            name=op.f("fk_core_notification_preferences_created_by_core_users"),
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["core_users.id"],
            name=op.f("fk_core_notification_preferences_updated_by_core_users"),
        ),
        sa.ForeignKeyConstraint(
            ["deleted_by"],
            ["core_users.id"],
            name=op.f("fk_core_notification_preferences_deleted_by_core_users"),
        ),
    )
    op.create_index(
        "uq_core_notification_preferences_scope",
        "core_notification_preferences",
        ["user_id", "channel", "module"],
        unique=True,
        postgresql_nulls_not_distinct=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_core_notification_preferences_user_id",
        "core_notification_preferences",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_table("core_notification_preferences")
    # The 'suppressed' enum value is intentionally left in place (PG cannot drop it).
