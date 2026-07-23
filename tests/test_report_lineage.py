"""Increment 4 Group F — report lineage (Blueprint Day-1 #17)."""

from sqlalchemy import func, select

from office_connect.core.models import AuditLog, ReportLineage
from office_connect.core.report_lineage import record_lineage


async def test_record_lineage_persists_provenance(app_session):
    row = await record_lineage(
        app_session,
        report_type="BAR-1",
        period="2026-Q1",
        source_filter={"fiscal_year": 2026, "quarter": 1, "status": "posted"},
        config_version="cfg-2026.1",
        module="reports",
    )
    await app_session.commit()

    loaded = (
        await app_session.execute(
            select(ReportLineage).where(ReportLineage.id == row.id)
        )
    ).scalar_one()
    assert loaded.report_type == "BAR-1"
    assert loaded.source_filter["fiscal_year"] == 2026
    assert loaded.generated_at is not None


async def test_lineage_is_unaudited(app_session, owner_session):
    """Report lineage is itself an immutable log — it does not write an audit
    row (it's in _UNAUDITED, like the query log)."""
    row = await record_lineage(
        app_session,
        report_type="FAR-4",
        source_filter={"month": "2026-07"},
    )
    await app_session.commit()

    audit_rows = (
        await owner_session.execute(
            select(func.count())
            .select_from(AuditLog)
            .where(
                AuditLog.table_name == "core_report_lineages",
                AuditLog.row_pk == row.id,
            )
        )
    ).scalar_one()
    assert audit_rows == 0
