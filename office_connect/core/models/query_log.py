"""Privacy-preserving read/query log (§14.7, Day-1 #5; append-only class).

``detail`` carries ids/params only — never data contents. The table exists
from Day 1; the middleware that populates it lands with auth in Phase 2.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from office_connect.core.base import Base, PKMixin


class QueryLog(PKMixin, Base):
    __tablename__ = "core_query_logs"
    __table_args__ = (
        Index("ix_core_query_logs_created_at", "created_at"),
        Index("ix_core_query_logs_created_by", "created_by"),
    )

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("core_users.id")
    )
    module: Mapped[str]
    resource: Mapped[str]
    action: Mapped[str] = mapped_column(server_default="read")
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    request_id: Mapped[str | None]
