"""attachments — content-addressed file service (core_attachments)

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-23

Increment 4 (spine amendments), master-plan §1.1 #2. Business table (mutable);
oc_app inherits SELECT/INSERT/UPDATE (no DELETE) from 0001 default privileges —
physical blob removal is a storage-layer action, never an SQL DELETE.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: Union[str, None] = "0005"
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
    scan_status = postgresql.ENUM(
        "pending", "clean", "infected", "error", name="core_attachment_scan_status"
    )
    scan_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "core_attachments",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("holder_kind", sa.String(), nullable=True),
        sa.Column("holder_id", sa.BigInteger(), nullable=True),
        sa.Column("original_filename", sa.String(), nullable=False),
        sa.Column("sniffed_mime", sa.String(), nullable=False),
        sa.Column("declared_mime", sa.String(), nullable=True),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(), nullable=False),
        sa.Column("storage_backend", sa.String(), nullable=False),
        sa.Column("media_kind", sa.String(), nullable=False),
        sa.Column("sanitized_sha256", sa.String(), nullable=True),
        sa.Column("sanitized_mime", sa.String(), nullable=True),
        sa.Column("sanitized_byte_size", sa.BigInteger(), nullable=True),
        sa.Column("sanitized_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "scan_status",
            postgresql.ENUM(name="core_attachment_scan_status", create_type=False),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("scan_signature", sa.String(), nullable=True),
        sa.Column("scanned_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("scanner_name", sa.String(), nullable=True),
        sa.Column(
            "retention_class", sa.String(), server_default="default", nullable=False
        ),
        sa.Column(
            "retention_starts_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "legal_hold", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("disposed_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("disposed_by", sa.BigInteger(), nullable=True),
        sa.Column("disposal_authority", sa.String(), nullable=True),
        *_audit_soft_delete_cols(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_core_attachments")),
    )
    op.create_index(
        "ix_core_attachments_holder",
        "core_attachments",
        ["holder_kind", "holder_id"],
    )
    op.create_index(
        "ix_core_attachments_scan_status", "core_attachments", ["scan_status"]
    )
    op.create_index("ix_core_attachments_sha256", "core_attachments", ["sha256"])
    op.create_index(
        "ix_core_attachments_legal_hold",
        "core_attachments",
        ["legal_hold"],
        postgresql_where=sa.text("legal_hold"),
    )
    op.create_index(
        "ix_core_attachments_retention_starts_at",
        "core_attachments",
        ["retention_starts_at"],
    )
    op.create_index(
        "ix_core_attachments_created_by", "core_attachments", ["created_by"]
    )


def downgrade() -> None:
    op.drop_table("core_attachments")
    postgresql.ENUM(name="core_attachment_scan_status").drop(
        op.get_bind(), checkfirst=True
    )
