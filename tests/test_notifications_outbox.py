"""QA gate: notification outbox — persist + dispatch + retry + dead-letter (Inc 4).

The Increment-3 caller-facing seam (``send_notification`` / ``send_test_email``)
is preserved; the body now persists a ``core_notifications`` row and dispatches.
Sync tests exercise the standalone seam (asyncio.run inside — no running loop);
async tests drive the primitives directly (no live Celery worker needed).
"""

import uuid

import pytest
from sqlalchemy import func, select

from office_connect.core.config import Settings
from office_connect.core.email import EmailError, EmailMessage
from office_connect.core.models import NotificationDelivery, NotificationOutbox
from office_connect.core.notifications import (
    Notification,
    dispatch_on_commit,
    dispatch_outbox_row,
    mark_dead,
    persist_notification,
    register_enqueuer,
    send_notification,
    send_test_email,
)
from office_connect.core.notifications import outbox as outbox_mod

# Explicit inline dispatch: the app container runs celery mode, but these tests
# exercise the synchronous seam and the async primitives directly.
_LOG = Settings(email_driver="log", notifications_dispatch="inline")


def _tok() -> str:
    return uuid.uuid4().hex[:12]


# --- sync seam contracts (unchanged from Increment 3) ---------------------


def test_send_test_email_returns_same_dict():
    result = send_test_email("ops@x", settings=_LOG)
    assert result["driver"] == "log"
    assert result["sent"] is False
    assert result["recipients"] == ["ops@x"]


def test_send_notification_email_channel():
    msg = EmailMessage(to="a@x", subject="s", text_body="b")
    result = send_notification(Notification(channel="email", email=msg), settings=_LOG)
    assert result.driver == "log"
    assert result.recipients == ["a@x"]


def test_email_notification_without_message_raises():
    with pytest.raises(EmailError):
        send_notification(Notification(channel="email", email=None), settings=_LOG)


def test_unknown_channel_raises():
    with pytest.raises(ValueError):
        send_notification(Notification(channel="sms"), settings=_LOG)


# --- outbox persistence + dispatch (async primitives) ---------------------


async def test_persist_creates_outbox_row(app_session):
    msg = EmailMessage(to="p@x", subject="persisted", text_body="b")
    nid = await persist_notification(
        app_session, Notification(channel="email", email=msg, meta={"module": "reimb"}),
        settings=_LOG,
    )
    await app_session.commit()
    row = (
        await app_session.execute(
            select(NotificationOutbox).where(NotificationOutbox.id == nid)
        )
    ).scalar_one()
    assert row.status == "queued"
    assert row.recipient_email == "p@x"
    assert row.module == "reimb"


async def test_dispatch_marks_sent_with_log_driver(app_session, owner_session):
    msg = EmailMessage(to="d@x", subject="dispatch", text_body="b")
    nid = await persist_notification(
        app_session, Notification(channel="email", email=msg), settings=_LOG
    )
    await app_session.commit()

    result = await dispatch_outbox_row(nid, settings=_LOG)
    assert result.driver == "log"

    row = (
        await owner_session.execute(
            select(NotificationOutbox).where(NotificationOutbox.id == nid)
        )
    ).scalar_one()
    assert row.status == "sent"
    assert row.sent_at is not None
    deliveries = list(
        (
            await owner_session.execute(
                select(NotificationDelivery).where(
                    NotificationDelivery.notification_id == nid
                )
            )
        ).scalars()
    )
    assert len(deliveries) == 1 and deliveries[0].outcome == "sent"


async def test_retry_path_on_failure(app_session, owner_session, monkeypatch):
    class _FailDriver:
        name = "fail"

        def send(self, message):
            raise EmailError("smtp down")

    monkeypatch.setattr(
        "office_connect.core.notifications.dispatch.get_email_driver",
        lambda settings: _FailDriver(),
    )
    msg = EmailMessage(to="f@x", subject="fail", text_body="b")
    nid = await persist_notification(
        app_session, Notification(channel="email", email=msg), settings=_LOG
    )
    await app_session.commit()

    with pytest.raises(EmailError):
        await dispatch_outbox_row(nid, settings=_LOG)

    row = (
        await owner_session.execute(
            select(NotificationOutbox).where(NotificationOutbox.id == nid)
        )
    ).scalar_one()
    assert row.status == "failed"
    assert row.attempt_count == 1
    assert row.last_error
    outcomes = list(
        (
            await owner_session.execute(
                select(NotificationDelivery.outcome).where(
                    NotificationDelivery.notification_id == nid
                )
            )
        ).scalars()
    )
    assert outcomes == ["failed"]


async def test_dead_letter_after_exhaustion(app_session, owner_session):
    msg = EmailMessage(to="x@x", subject="dead", text_body="b")
    nid = await persist_notification(
        app_session, Notification(channel="email", email=msg), settings=_LOG
    )
    await app_session.commit()

    await mark_dead(nid, "gave up after retries", settings=_LOG)

    row = (
        await owner_session.execute(
            select(NotificationOutbox).where(NotificationOutbox.id == nid)
        )
    ).scalar_one()
    assert row.status == "dead"
    # Surfaces in a failed-jobs / dead-letter query.
    dead = (
        await owner_session.execute(
            select(func.count())
            .select_from(NotificationOutbox)
            .where(NotificationOutbox.status == "dead", NotificationOutbox.id == nid)
        )
    ).scalar_one()
    assert dead == 1


async def test_dedup_key_prevents_duplicate(app_session, owner_session):
    key = _tok()
    msg = EmailMessage(to="dup@x", subject="dup", text_body="b")
    first = await persist_notification(
        app_session,
        Notification(channel="email", email=msg, meta={"dedup_key": key}),
        settings=_LOG,
    )
    await app_session.commit()
    # App-level dedup: the second persist returns the same row, no new insert.
    second = await persist_notification(
        app_session,
        Notification(channel="email", email=msg, meta={"dedup_key": key}),
        settings=_LOG,
    )
    assert second == first

    # DB backstop: a raw duplicate (bypassing the app check) hits the partial unique.
    owner_session.add(
        NotificationOutbox(
            channel="email", subject="dup", recipient_email="dup@x", dedup_key=key
        )
    )
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        await owner_session.commit()
    await owner_session.rollback()


async def test_dispatch_on_commit_enqueues_after_commit(app_session):
    captured: list[int] = []
    previous = outbox_mod._enqueuer
    register_enqueuer(captured.append)
    try:
        msg = EmailMessage(to="c@x", subject="commit", text_body="b")
        nid = await persist_notification(
            app_session, Notification(channel="email", email=msg), settings=_LOG
        )
        dispatch_on_commit(app_session, nid)
        assert captured == []  # not yet — only after commit
        await app_session.commit()
        assert captured == [nid]
    finally:
        outbox_mod._enqueuer = previous
