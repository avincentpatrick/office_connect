"""QA gate (rule 6): default filter, escape hatch, and audit linkage."""

from datetime import date

from sqlalchemy import select

from office_connect.core.models import Activity, AuditLog
from office_connect.core.soft_delete import soft_delete


async def test_soft_delete_sets_columns_and_hides_row(app_session):
    activity = Activity(title="Soft delete test", date_start=date(2026, 7, 22))
    app_session.add(activity)
    await app_session.commit()
    pk = activity.id

    soft_delete(activity, actor_id=None)
    await app_session.commit()
    assert activity.deleted_at is not None

    # Default select no longer sees it…
    hidden = (
        await app_session.execute(select(Activity).where(Activity.id == pk))
    ).scalar_one_or_none()
    assert hidden is None

    # …the escape hatch does.
    found = (
        await app_session.execute(
            select(Activity)
            .where(Activity.id == pk)
            .execution_options(include_deleted=True)
        )
    ).scalar_one_or_none()
    assert found is not None
    assert found.deleted_at is not None


async def test_soft_delete_is_idempotent(app_session):
    activity = Activity(title="Idempotent SD", date_start=date(2026, 7, 22))
    app_session.add(activity)
    await app_session.commit()

    soft_delete(activity)
    await app_session.commit()
    first_deleted_at = activity.deleted_at

    soft_delete(activity)  # second call is a no-op
    await app_session.commit()
    assert activity.deleted_at == first_deleted_at


async def test_soft_delete_writes_audit_row(app_session, owner_session):
    activity = Activity(title="SD audit row", date_start=date(2026, 7, 22))
    app_session.add(activity)
    await app_session.commit()
    soft_delete(activity, actor_id=None)
    await app_session.commit()

    actions = list(
        (
            await owner_session.execute(
                select(AuditLog.action)
                .where(
                    AuditLog.table_name == "core_activities",
                    AuditLog.row_pk == activity.id,
                )
                .order_by(AuditLog.id)
            )
        ).scalars()
    )
    assert actions == ["insert", "soft_delete"]
