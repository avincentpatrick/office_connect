"""QA gate: notification outbox stub + test-email path (Increment 3).

The stub routes email notifications through the selected driver (log in dev).
Durable outbox tables land in Increment 4 — this pins the caller-facing seam.
"""

import pytest

from office_connect.core.config import Settings
from office_connect.core.email import EmailError, EmailMessage
from office_connect.core.notifications import Notification, send_notification, send_test_email

_LOG = Settings(email_driver="log")


def test_send_test_email_via_log_driver():
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
