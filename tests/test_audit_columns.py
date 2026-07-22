"""QA gate (rule 5): mandatory ownership columns auto-populate."""

from datetime import date

from office_connect.core.models import Activity


async def test_insert_populates_audit_columns(app_session):
    activity = Activity(title="Audit columns test", date_start=date(2026, 7, 22))
    app_session.add(activity)
    await app_session.commit()
    await app_session.refresh(activity)

    assert activity.created_at is not None
    assert activity.updated_at is not None
    assert activity.deleted_at is None


async def test_update_advances_updated_at_only(app_session):
    activity = Activity(title="Updated-at test", date_start=date(2026, 7, 22))
    app_session.add(activity)
    await app_session.commit()
    await app_session.refresh(activity)
    created_at = activity.created_at
    first_updated_at = activity.updated_at

    activity.venue = "Conference Room A"
    await app_session.commit()
    await app_session.refresh(activity)

    assert activity.created_at == created_at  # never rewritten
    assert activity.updated_at > first_updated_at
