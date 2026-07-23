"""QA gate (rules 5+6): the runtime role physically cannot UPDATE/DELETE what
it must not — grants enforced in migration 0001, probed here as oc_app."""

from datetime import date

import pytest
from sqlalchemy import text, update
from sqlalchemy.exc import DBAPIError

from office_connect.core.models import Activity

DENIED_STATEMENTS = [
    "UPDATE core_audit_logs SET request_id = 'x' WHERE id = 1",
    "DELETE FROM core_audit_logs WHERE id = 1",
    "UPDATE core_query_logs SET action = 'x' WHERE id = 1",
    "DELETE FROM core_query_logs WHERE id = 1",
    "UPDATE core_notification_deliveries SET outcome = 'sent' WHERE id = 1",
    "DELETE FROM core_notification_deliveries WHERE id = 1",
    "UPDATE core_report_lineages SET report_type = 'x' WHERE id = 1",
    "DELETE FROM core_report_lineages WHERE id = 1",
    "DELETE FROM core_activities WHERE id = 1",
    "DELETE FROM core_attachments WHERE id = 1",
    "DELETE FROM core_notifications WHERE id = 1",
    "DELETE FROM core_feature_flags WHERE id = 1",
    "DELETE FROM core_tenant_configs WHERE id = 1",
    "TRUNCATE core_audit_logs",
]


@pytest.mark.parametrize("statement", DENIED_STATEMENTS)
async def test_oc_app_denied(app_session, statement):
    with pytest.raises(DBAPIError) as excinfo:
        await app_session.execute(text(statement))
    assert "permission denied" in str(excinfo.value).lower()
    await app_session.rollback()


async def test_oc_app_can_insert_into_audit_log(app_session):
    """INSERT is granted (append-only). Rolled back so the ad-hoc row never
    lands in the chain."""
    await app_session.execute(
        text(
            "INSERT INTO core_audit_logs "
            "(created_at, table_name, row_pk, action, prev_hash, row_hash) "
            "VALUES (now(), 'probe', 1, 'insert', repeat('0', 64), repeat('9', 64))"
        )
    )
    await app_session.rollback()


async def test_orm_hard_delete_blocked_before_reaching_db(app_session):
    """Belt & braces: session.delete() raises at flush (audit listener guard)."""
    activity = Activity(title="Delete guard", date_start=date(2026, 7, 22))
    app_session.add(activity)
    await app_session.commit()

    await app_session.delete(activity)
    with pytest.raises(RuntimeError, match="Hard deletes are forbidden"):
        await app_session.flush()
    await app_session.rollback()


async def test_orm_bulk_update_blocked(app_session):
    """Bulk ORM UPDATE bypasses the unit of work (no audit rows) — forbidden
    (rule 5); the sanctioned escape hatch is allow_unaudited=True."""
    with pytest.raises(RuntimeError, match="Bulk ORM UPDATE/DELETE"):
        await app_session.execute(
            update(Activity).where(Activity.id == -1).values(venue="bulk")
        )
    await app_session.rollback()
