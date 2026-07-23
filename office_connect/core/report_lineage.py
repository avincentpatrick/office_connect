"""Report-lineage recording helper — one call every generator uses from Day 1.

Records the provenance of a generated output so any figure is traceable to its
source rows (Blueprint Day-1 #17). Append-only + unaudited, so this is a plain
INSERT (no hash-chain row).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.models.report_lineage import ReportLineage
from office_connect.core.time import utc_now


async def record_lineage(
    session: AsyncSession,
    *,
    report_type: str,
    source_filter: dict[str, Any],
    period: str | None = None,
    config_version: str | None = None,
    generated_by: int | None = None,
    generated_at: datetime | None = None,
    archived_key: str | None = None,
    module: str | None = None,
    activity_id: int | None = None,
    notes: str | None = None,
) -> ReportLineage:
    """Persist a lineage row for a generated report; returns the flushed row."""
    row = ReportLineage(
        report_type=report_type,
        source_filter=source_filter,
        period=period,
        config_version=config_version,
        generated_by=generated_by,
        generated_at=generated_at or utc_now(),
        archived_key=archived_key,
        module=module,
        activity_id=activity_id,
        notes=notes,
    )
    session.add(row)
    await session.flush()
    return row
