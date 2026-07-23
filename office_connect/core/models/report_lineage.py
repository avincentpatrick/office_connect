"""Report lineage — every generated government output records its provenance.

Master-plan §1.1 #10 + Blueprint Day-1 #17: any figure in any submitted report
must be traceable to the underlying records (an ISO 9001 + COA expectation). Each
generation records the report type, period, the **source-row filter used**, the
config version, who/when, and the archived copy's storage key.

Append-only (write-once provenance): ``created_*`` only, REVOKE UPDATE, unaudited
(it is itself an immutable log, like ``core_query_logs``). Folded into ``core``
per master-plan §4 #7 — no ``rpt_`` tables until a real table need appears.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from office_connect.core.base import Base, PKMixin


class ReportLineage(PKMixin, Base):
    __tablename__ = "core_report_lineages"
    __table_args__ = (
        Index("ix_core_report_lineages_report_type", "report_type"),
        Index("ix_core_report_lineages_generated_at", "generated_at"),
        Index("ix_core_report_lineages_activity_id", "activity_id"),
    )

    report_type: Mapped[str]
    period: Mapped[str | None]
    source_filter: Mapped[dict[str, Any]] = mapped_column(JSONB)
    config_version: Mapped[str | None]
    generated_by: Mapped[int | None] = mapped_column(BigInteger)  # future FK
    generated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    archived_key: Mapped[str | None]  # storage SHA-256 of the archived copy
    module: Mapped[str | None]
    activity_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("core_activities.id")
    )
    notes: Mapped[str | None] = mapped_column(Text)
    # Append-only mandatory column (§6): created_* only — no updated_*/deleted_*.
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    created_by: Mapped[int | None] = mapped_column(BigInteger)  # future FK
