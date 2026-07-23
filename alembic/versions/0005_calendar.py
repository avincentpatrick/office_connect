"""calendar spine — holidays/suspensions + statutory compliance deadlines

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-23

Increment 4 (spine amendments), master-plan §1.1 #6 & #11. Both lookup tables
(mutable; oc_app inherits SELECT/INSERT/UPDATE, no DELETE). Rows seeded by the
Group-G seed framework — the 21 §3.4 statutory deadlines + PH holidays.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: Union[str, None] = "0004"
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
    holiday_type = postgresql.ENUM(
        "regular",
        "special_non_working",
        "special_working",
        "work_suspension",
        "local",
        name="core_holiday_type",
    )
    holiday_type.create(op.get_bind(), checkfirst=True)
    holiday_scope = postgresql.ENUM(
        "national", "local", name="core_holiday_scope"
    )
    holiday_scope.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "core_holidays",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("calendar_date", sa.Date(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column(
            "holiday_type",
            postgresql.ENUM(name="core_holiday_type", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "scope",
            postgresql.ENUM(name="core_holiday_scope", create_type=False),
            server_default="national",
            nullable=False,
        ),
        sa.Column("locality", sa.String(), nullable=True),
        sa.Column("proclamation_ref", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        *_audit_soft_delete_cols(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_core_holidays")),
    )
    op.create_index("ix_core_holidays_calendar_date", "core_holidays", ["calendar_date"])
    op.create_index("ix_core_holidays_holiday_type", "core_holidays", ["holiday_type"])
    op.create_index(
        "uq_core_holidays_date_name_scope",
        "core_holidays",
        ["calendar_date", "name", "scope"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    cadence = postgresql.ENUM(
        "annual",
        "semiannual",
        "quarterly",
        "monthly",
        "per_event",
        "custom",
        name="core_deadline_cadence",
    )
    cadence.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "core_compliance_deadlines",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("authority", sa.String(), nullable=False),
        sa.Column(
            "cadence",
            postgresql.ENUM(name="core_deadline_cadence", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "due_rule",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "use_working_day_math",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.BigInteger(), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        *_audit_soft_delete_cols(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_core_compliance_deadlines")),
    )
    op.create_index(
        "uq_core_compliance_deadlines_default",
        "core_compliance_deadlines",
        ["code", "effective_from"],
        unique=True,
        postgresql_where=sa.text("tenant_id IS NULL AND deleted_at IS NULL"),
    )
    op.create_index(
        "uq_core_compliance_deadlines_tenant",
        "core_compliance_deadlines",
        ["code", "tenant_id", "effective_from"],
        unique=True,
        postgresql_where=sa.text("tenant_id IS NOT NULL AND deleted_at IS NULL"),
    )
    op.create_index(
        "ix_core_compliance_deadlines_code", "core_compliance_deadlines", ["code"]
    )
    op.create_index(
        "ix_core_compliance_deadlines_tenant_id",
        "core_compliance_deadlines",
        ["tenant_id"],
    )
    op.create_index(
        "ix_core_compliance_deadlines_cadence",
        "core_compliance_deadlines",
        ["cadence"],
    )


def downgrade() -> None:
    op.drop_table("core_compliance_deadlines")
    postgresql.ENUM(name="core_deadline_cadence").drop(op.get_bind(), checkfirst=True)
    op.drop_table("core_holidays")
    postgresql.ENUM(name="core_holiday_scope").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="core_holiday_type").drop(op.get_bind(), checkfirst=True)
