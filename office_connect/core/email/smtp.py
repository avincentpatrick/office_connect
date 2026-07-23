"""SMTP email driver (stdlib ``smtplib`` — the on-prem default transport).

Connects to ``settings.smtp_host:smtp_port``, upgrades to TLS with STARTTLS
(port 587), authenticates when a user is configured, and sends the shared MIME.
No third-party dependency.
"""

from __future__ import annotations

import smtplib

from office_connect.core.config import Settings, get_settings
from office_connect.core.email._mime import build_mime
from office_connect.core.email.base import EmailDriver, EmailError, EmailMessage, SendResult


class SMTPEmailDriver(EmailDriver):
    name = "smtp"

    def __init__(self, settings: Settings | None = None) -> None:
        settings = settings or get_settings()
        self._host = settings.smtp_host
        self._port = settings.smtp_port
        self._user = settings.smtp_user
        self._password = settings.smtp_password
        self._default_sender = settings.smtp_from

    def send(self, message: EmailMessage) -> SendResult:
        if not self._host:
            raise EmailError("smtp email needs SMTP_HOST")
        sender = self._resolve_sender(message, self._default_sender)
        mime = build_mime(message, sender)
        try:
            with smtplib.SMTP(self._host, self._port, timeout=30) as client:
                client.ehlo()
                if self._port == 587 or client.has_extn("starttls"):
                    client.starttls()
                    client.ehlo()
                if self._user:
                    client.login(self._user, self._password or "")
                client.send_message(mime, from_addr=sender, to_addrs=message.recipients)
        except (smtplib.SMTPException, OSError) as exc:
            raise EmailError(f"smtp send failed: {exc}") from exc
        return SendResult(driver=self.name, sent=True, recipients=message.recipients)
