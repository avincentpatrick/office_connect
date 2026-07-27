"""Stage B (Phase 2) Increment 4 — notification recipient/prefs resolution.

Closes the Increment-4 recipient seam: a notification addressed only by
``recipient_user_id`` resolves the login's email (falling back to the linked
staff record), and per-user delivery preferences suppress opted-out channels —
except security/transactional notifications, which can never be silenced.
Service-layer tests (no HTTP surface, no live worker) mirroring
``test_notifications_outbox.py``.
"""

import uuid

from sqlalchemy import func, select

from office_connect.core.config import Settings
from office_connect.core.email import EmailMessage
from office_connect.core.models import (
    NotificationDelivery,
    NotificationOutbox,
    NotificationPreference,
    Staff,
    User,
)
from office_connect.core.notifications import (
    Notification,
    dispatch_outbox_row,
    persist_notification,
)
from office_connect.core.soft_delete import soft_delete

_LOG = Settings(email_driver="log", notifications_dispatch="inline")


def _tok() -> str:
    return uuid.uuid4().hex[:12]


async def _row(session, nid: int) -> NotificationOutbox:
    return (
        await session.execute(
            select(NotificationOutbox).where(NotificationOutbox.id == nid)
        )
    ).scalar_one()


async def test_resolve_user_id_to_email(app_session, make_user):
    user, _ = await make_user()
    nid = await persist_notification(
        app_session,
        Notification(channel="email", meta={"recipient_user_id": user.id}),
        settings=_LOG,
    )
    await app_session.commit()
    row = await _row(app_session, nid)
    assert row.recipient_email == user.email
    assert row.recipient_user_id == user.id
    assert row.status == "queued"


async def test_explicit_email_precedence(app_session, make_user):
    user, _ = await make_user()
    msg = EmailMessage(to="explicit@x", subject="s", text_body="b")
    nid = await persist_notification(
        app_session,
        Notification(channel="email", email=msg, meta={"recipient_user_id": user.id}),
        settings=_LOG,
    )
    await app_session.commit()
    row = await _row(app_session, nid)
    assert row.recipient_email == "explicit@x"  # explicit address wins
    assert row.recipient_user_id == user.id  # still recorded


async def test_staff_email_fallback(app_session):
    staff = Staff(
        employee_no=f"E-{_tok()}",
        given_name="G",
        surname="S",
        full_name="G S",
        email=f"staff-{_tok()}@doh.gov",
    )
    app_session.add(staff)
    await app_session.flush()
    # A login with no email of its own (defensive path — User.email is normally set).
    user = User(email="", staff_id=staff.id, is_active=True)
    app_session.add(user)
    await app_session.commit()

    nid = await persist_notification(
        app_session,
        Notification(channel="email", meta={"recipient_user_id": user.id}),
        settings=_LOG,
    )
    await app_session.commit()
    row = await _row(app_session, nid)
    assert row.recipient_email == staff.email

    # Keep the empty-email row out of the live partial-unique index across reruns.
    soft_delete(user)
    await app_session.commit()


async def test_unresolvable_user_is_suppressed(app_session):
    # A soft-deleted user still satisfies the FK, but the soft-delete filter hides
    # it from resolution → no address → suppressed (never dead-lettered).
    user = User(email=f"gone-{_tok()}@doh.gov", is_active=True)
    app_session.add(user)
    await app_session.flush()
    soft_delete(user)
    await app_session.commit()

    nid = await persist_notification(
        app_session,
        Notification(channel="email", meta={"recipient_user_id": user.id}),
        settings=_LOG,
    )
    await app_session.commit()
    row = await _row(app_session, nid)
    assert row.status == "suppressed"
    assert row.recipient_email is None


async def test_pref_opt_out_suppresses(app_session, make_user):
    user, _ = await make_user()
    app_session.add(
        NotificationPreference(
            user_id=user.id, channel="email", module="reimb", enabled=False
        )
    )
    await app_session.commit()
    nid = await persist_notification(
        app_session,
        Notification(
            channel="email",
            meta={"recipient_user_id": user.id, "module": "reimb"},
        ),
        settings=_LOG,
    )
    await app_session.commit()
    assert (await _row(app_session, nid)).status == "suppressed"


async def test_pref_default_enabled_when_no_row(app_session, make_user):
    user, _ = await make_user()
    nid = await persist_notification(
        app_session,
        Notification(
            channel="email",
            meta={"recipient_user_id": user.id, "module": "reimb"},
        ),
        settings=_LOG,
    )
    await app_session.commit()
    assert (await _row(app_session, nid)).status == "queued"


async def test_module_pref_overrides_default(app_session, make_user):
    user, _ = await make_user()
    app_session.add(
        NotificationPreference(
            user_id=user.id, channel="email", module=None, enabled=False
        )
    )
    app_session.add(
        NotificationPreference(
            user_id=user.id, channel="email", module="reimb", enabled=True
        )
    )
    await app_session.commit()

    # reimb → module-specific row wins → queued
    reimb = await persist_notification(
        app_session,
        Notification(
            channel="email", meta={"recipient_user_id": user.id, "module": "reimb"}
        ),
        settings=_LOG,
    )
    await app_session.commit()
    assert (await _row(app_session, reimb)).status == "queued"

    # a different module → falls back to the disabled default → suppressed
    other = await persist_notification(
        app_session,
        Notification(
            channel="email", meta={"recipient_user_id": user.id, "module": "other"}
        ),
        settings=_LOG,
    )
    await app_session.commit()
    assert (await _row(app_session, other)).status == "suppressed"


async def test_security_class_bypasses_prefs(app_session, make_user):
    user, _ = await make_user()
    app_session.add(
        NotificationPreference(
            user_id=user.id, channel="email", module=None, enabled=False
        )
    )
    await app_session.commit()
    nid = await persist_notification(
        app_session,
        Notification(
            channel="email",
            meta={"recipient_user_id": user.id, "notification_class": "security"},
        ),
        settings=_LOG,
    )
    await app_session.commit()
    assert (await _row(app_session, nid)).status == "queued"


async def test_suppressed_not_dispatched(app_session, owner_session, make_user):
    user, _ = await make_user()
    app_session.add(
        NotificationPreference(
            user_id=user.id, channel="email", module=None, enabled=False
        )
    )
    await app_session.commit()
    nid = await persist_notification(
        app_session,
        Notification(channel="email", meta={"recipient_user_id": user.id}),
        settings=_LOG,
    )
    await app_session.commit()

    result = await dispatch_outbox_row(nid, settings=_LOG)
    assert result.sent is False
    assert result.driver == "suppressed"

    row = (
        await owner_session.execute(
            select(NotificationOutbox).where(NotificationOutbox.id == nid)
        )
    ).scalar_one()
    assert row.status == "suppressed"
    deliveries = (
        await owner_session.execute(
            select(func.count())
            .select_from(NotificationDelivery)
            .where(NotificationDelivery.notification_id == nid)
        )
    ).scalar_one()
    assert deliveries == 0


async def test_dedup_short_circuits_before_resolution(app_session, make_user):
    user, _ = await make_user()
    key = _tok()
    msg = EmailMessage(to="dup@x", subject="s", text_body="b")
    first = await persist_notification(
        app_session,
        Notification(channel="email", email=msg, meta={"dedup_key": key}),
        settings=_LOG,
    )
    await app_session.commit()
    second = await persist_notification(
        app_session,
        Notification(channel="email", email=msg, meta={"dedup_key": key}),
        settings=_LOG,
    )
    assert second == first  # same row; resolver not re-run
