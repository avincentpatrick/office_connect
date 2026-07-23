"""activity taxonomy — configurable GAD/CCET/DRR/UHC tags + assignments

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-23

Increment 4 (spine amendments), master-plan §1.1 #15. Attribution taxonomies are
configurable rows, never boolean columns:
- core_activity_tags (lookup) — the vocabulary.
- core_activity_tag_assignments (business) — activity ↔ tag edges (multi-tag).

Both are mutable tables; oc_app inherits SELECT/INSERT/UPDATE (no DELETE) from
0001's default privileges — no grant change needed.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _audit_soft_delete_cols() -> list[sa.Column]:
    """Mandatory business/lookup columns (database-standards.md §6)."""
    return [
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("created_by", sa.BigInteger(), nullable=True),  # FK → core_users (Phase 2)
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
    taxonomy = postgresql.ENUM(
        "gad", "ccet", "drr", "uhc", name="core_activity_taxonomy"
    )
    taxonomy.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "core_activity_tags",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column(
            "taxonomy",
            postgresql.ENUM(name="core_activity_taxonomy", create_type=False),
            nullable=False,
        ),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        *_audit_soft_delete_cols(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_core_activity_tags")),
    )
    op.create_index(
        "uq_core_activity_tags_taxonomy_code",
        "core_activity_tags",
        ["taxonomy", "code"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_core_activity_tags_taxonomy", "core_activity_tags", ["taxonomy"]
    )

    op.create_table(
        "core_activity_tag_assignments",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("activity_id", sa.BigInteger(), nullable=False),
        sa.Column("activity_tag_id", sa.BigInteger(), nullable=False),
        *_audit_soft_delete_cols(),
        sa.PrimaryKeyConstraint(
            "id", name=op.f("pk_core_activity_tag_assignments")
        ),
        sa.ForeignKeyConstraint(
            ["activity_id"],
            ["core_activities.id"],
            name=op.f(
                "fk_core_activity_tag_assignments_activity_id_core_activities"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["activity_tag_id"],
            ["core_activity_tags.id"],
            name=op.f(
                "fk_core_activity_tag_assignments_activity_tag_id_core_activity_tags"
            ),
        ),
    )
    op.create_index(
        "uq_core_activity_tag_assignments_activity_tag",
        "core_activity_tag_assignments",
        ["activity_id", "activity_tag_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_core_activity_tag_assignments_activity_id",
        "core_activity_tag_assignments",
        ["activity_id"],
    )
    op.create_index(
        "ix_core_activity_tag_assignments_activity_tag_id",
        "core_activity_tag_assignments",
        ["activity_tag_id"],
    )


def downgrade() -> None:
    op.drop_table("core_activity_tag_assignments")
    op.drop_table("core_activity_tags")
    postgresql.ENUM(name="core_activity_taxonomy").drop(
        op.get_bind(), checkfirst=True
    )
