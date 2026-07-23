"""QA gate: email drivers + selection (Increment 3).

Log driver needs nothing; SMTP is tested with ``smtplib.SMTP`` monkeypatched
(no real server); Gmail with the API client mocked (no real creds).
"""

import base64
import smtplib
from unittest.mock import MagicMock

import pytest

from office_connect.core.config import Settings
from office_connect.core.email import (
    EmailError,
    EmailMessage,
    get_email_driver,
    resolve_email_driver_name,
)
from office_connect.core.email.gmail import GmailEmailDriver
from office_connect.core.email.log import LogEmailDriver
from office_connect.core.email.smtp import SMTPEmailDriver


# ----------------------------------------------------------- message + select
def test_message_normalizes_recipients():
    msg = EmailMessage(to="a@x", subject="s", text_body="b")
    assert msg.to == ["a@x"]
    assert msg.recipients == ["a@x"]


def test_message_requires_recipient_and_subject():
    with pytest.raises(EmailError):
        EmailMessage(to=[], subject="s", text_body="b")
    with pytest.raises(EmailError):
        EmailMessage(to="a@x", subject="", text_body="b")


def test_driver_selection():
    assert resolve_email_driver_name(Settings(smtp_host=None, email_driver=None)) == "log"
    assert resolve_email_driver_name(Settings(smtp_host="mail", email_driver=None)) == "smtp"
    assert resolve_email_driver_name(Settings(email_driver="gmail")) == "gmail"
    assert isinstance(get_email_driver(Settings()), LogEmailDriver)
    assert isinstance(get_email_driver(Settings(smtp_host="mail")), SMTPEmailDriver)


# ------------------------------------------------------------------- log driver
def test_log_driver_records_not_sends():
    result = LogEmailDriver().send(EmailMessage(to="a@x", subject="s", text_body="b"))
    assert result.driver == "log"
    assert result.sent is False
    assert result.recipients == ["a@x"]


# ------------------------------------------------------------------ smtp driver
class _FakeSMTP:
    instances: list["_FakeSMTP"] = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port = host, port
        self.started_tls = False
        self.logged_in = None
        self.sent = None
        _FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def ehlo(self):
        pass

    def has_extn(self, name):
        return True

    def starttls(self):
        self.started_tls = True

    def login(self, user, password):
        self.logged_in = (user, password)

    def send_message(self, mime, from_addr=None, to_addrs=None):
        self.sent = {"from": from_addr, "to": to_addrs, "subject": mime["Subject"]}


def test_smtp_driver_sends(monkeypatch):
    _FakeSMTP.instances.clear()
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    driver = SMTPEmailDriver(
        Settings(smtp_host="mail", smtp_port=587, smtp_user="u", smtp_password="p",
                 smtp_from="from@x")
    )
    result = driver.send(EmailMessage(to="to@x", subject="Hi", text_body="body"))

    assert result.sent is True
    assert result.driver == "smtp"
    conn = _FakeSMTP.instances[-1]
    assert conn.started_tls is True         # STARTTLS on 587
    assert conn.logged_in == ("u", "p")
    assert conn.sent == {"from": "from@x", "to": ["to@x"], "subject": "Hi"}


def test_smtp_driver_requires_host():
    with pytest.raises(EmailError):
        SMTPEmailDriver(Settings(smtp_host=None)).send(
            EmailMessage(to="a@x", subject="s", text_body="b")
        )


# ------------------------------------------------------------------ gmail driver
def test_gmail_driver_sends():
    svc = MagicMock()
    send_call = svc.users.return_value.messages.return_value.send
    send_call.return_value.execute.return_value = {"id": "msg-123"}

    driver = GmailEmailDriver(Settings(gmail_sender="sender@x"))
    driver._svc = svc  # inject mocked client
    result = driver.send(EmailMessage(to="to@x", subject="Hi", text_body="body"))

    assert result.sent is True
    assert result.message_id == "msg-123"
    _, kwargs = send_call.call_args
    assert kwargs["userId"] == "sender@x"
    # raw is base64url of a MIME that carries the subject.
    decoded = base64.urlsafe_b64decode(kwargs["body"]["raw"]).decode()
    assert "Subject: Hi" in decoded
