"""report lineage — provenance of every generated government output

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-23

Increment 4 (spine amendments), master-plan §1.1 #10 / Blueprint Day-1 #17.
Append-only (created_* only) — MUST REVOKE UPDATE from oc_app.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "core_report_lineages",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("report_type", sa.String(), nullable=False),
        sa.Column("period", sa.String(), nullable=True),
        sa.Column("source_filter", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("config_version", sa.String(), nullable=True),
        sa.Column("generated_by", sa.BigInteger(), nullable=True),
        sa.Column("generated_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("archived_key", sa.String(), nullable=True),
        sa.Column("module", sa.String(), nullable=True),
        sa.Column("activity_id", sa.BigInteger(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_core_report_lineages")),
        sa.ForeignKeyConstraint(
            ["activity_id"],
            ["core_activities.id"],
            name=op.f("fk_core_report_lineages_activity_id_core_activities"),
        ),
    )
    op.create_index(
        "ix_core_report_lineages_report_type", "core_report_lineages", ["report_type"]
    )
    op.create_index(
        "ix_core_report_lineages_generated_at", "core_report_lineages", ["generated_at"]
    )
    op.create_index(
        "ix_core_report_lineages_activity_id", "core_report_lineages", ["activity_id"]
    )
    # Append-only: revoke the UPDATE that default privileges grant to future tables.
    op.execute("REVOKE UPDATE ON core_report_lineages FROM oc_app")


def downgrade() -> None:
    op.drop_table("core_report_lineages")
