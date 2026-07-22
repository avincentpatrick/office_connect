"""Hash-chained, append-only audit trail (Day-1 #3; standing rule 5).

Append-only class (database-standards.md §6): ``created_at`` + actor only —
no ``updated_*``/``deleted_*`` columns, and the app role (``oc_app``) has no
UPDATE/DELETE on it. ``created_at`` is APP-SET (never server_default) because
it is inside the hash — a timestamp can never be rewritten without breaking
the chain (CSS-IS lesson). Rows are written exclusively by the listeners in
``core/audit.py``; the chain's genesis ``prev_hash`` is 64 zeros.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, Identity, Index
from sqlalchemy.dialects.postgresql import CHAR, JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from office_connect.core.base import Base


class AuditLog(Base):
    __tablename__ = "core_audit_logs"
    __table_args__ = (
        CheckConstraint(
            "action IN ('insert', 'update', 'soft_delete')", name="action"
        ),
        Index("ix_core_audit_logs_table_name_row_pk", "table_name", "row_pk"),
        Index("ix_core_audit_logs_created_at", "created_at"),
    )

    # GENERATED ALWAYS — nobody may insert an explicit id into the chain.
    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))  # app-set
    actor_id: Mapped[int | None] = mapped_column(BigInteger)  # future FK core_users.id
    request_id: Mapped[str | None]
    table_name: Mapped[str]
    row_pk: Mapped[int] = mapped_column(BigInteger)
    action: Mapped[str]
    old_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    new_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    prev_hash: Mapped[str] = mapped_column(CHAR(64))
    row_hash: Mapped[str] = mapped_column(CHAR(64), unique=True)
