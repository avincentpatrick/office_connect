"""UACS / PREXC codes — per-FY PAP tree + object codes (effective-dated)

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-23

Increment 4 (spine amendments), master-plan §1.1 #15. Both lookup tables;
oc_app inherits SELECT/INSERT/UPDATE (no DELETE) from 0001 default privileges —
no grant change. Rows are seeded by the Group-G seed framework, not here.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, None] = "0003"
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
    pap_level = postgresql.ENUM(
        "cost_structure",
        "oo",
        "program",
        "subprogram",
        "activity",
        "project",
        name="core_pap_level",
    )
    pap_level.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "core_pap_codes",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("uacs_code", sa.String(), nullable=False),
        sa.Column(
            "level",
            postgresql.ENUM(name="core_pap_level", create_type=False),
            nullable=False,
        ),
        sa.Column("parent_id", sa.BigInteger(), nullable=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        *_audit_soft_delete_cols(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_core_pap_codes")),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["core_pap_codes.id"],
            name=op.f("fk_core_pap_codes_parent_id_core_pap_codes"),
        ),
    )
    op.create_index(
        "uq_core_pap_codes_fiscal_year_uacs_code",
        "core_pap_codes",
        ["fiscal_year", "uacs_code"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index("ix_core_pap_codes_fiscal_year", "core_pap_codes", ["fiscal_year"])
    op.create_index("ix_core_pap_codes_uacs_code", "core_pap_codes", ["uacs_code"])
    op.create_index("ix_core_pap_codes_parent_id", "core_pap_codes", ["parent_id"])
    op.create_index("ix_core_pap_codes_level", "core_pap_codes", ["level"])

    op.create_table(
        "core_object_codes",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("uacs_object_code", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        *_audit_soft_delete_cols(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_core_object_codes")),
    )
    op.create_index(
        "uq_core_object_codes_code_effective_from",
        "core_object_codes",
        ["uacs_object_code", "effective_from"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_core_object_codes_uacs_object_code",
        "core_object_codes",
        ["uacs_object_code"],
    )


def downgrade() -> None:
    op.drop_table("core_object_codes")
    op.drop_table("core_pap_codes")
    postgresql.ENUM(name="core_pap_level").drop(op.get_bind(), checkfirst=True)
