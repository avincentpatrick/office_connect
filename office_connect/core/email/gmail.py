"""Gmail API email driver (kept for tenants that send through Google Workspace).

Uses a service account with **domain-wide delegation** to impersonate the
configured ``gmail_sender`` and calls ``users.messages.send`` with the shared
MIME, base64url-encoded. The google libraries and client are imported lazily so
importing this module needs neither the packages nor credentials — SMTP is the
default and must not pay for Google being installed.
"""

from __future__ import annotations

import base64

from office_connect.core.config import Settings, get_settings
from office_connect.core.email._mime import build_mime
from office_connect.core.email.base import EmailDriver, EmailError, EmailMessage, SendResult

_SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


class GmailEmailDriver(EmailDriver):
    name = "gmail"

    def __init__(self, settings: Settings | None = None) -> None:
        settings = settings or get_settings()
        self._creds_path = settings.google_credentials_path
        # Delegated sender to impersonate; falls back to SMTP_FROM.
        self._sender = settings.gmail_sender or settings.smtp_from
        self._svc = None

    def _service(self):
        if self._svc is not None:
            return self._svc
        if not self._creds_path:
            raise EmailError("gmail email needs GOOGLE_CREDENTIALS_PATH")
        if not self._sender:
            raise EmailError("gmail email needs GMAIL_SENDER (delegated sender)")
        try:
            from google.oauth2 import service_account  # noqa: PLC0415
            from googleapiclient.discovery import build  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover - deps ship in the image
            raise EmailError(
                "gmail email requires google-api-python-client + google-auth"
            ) from exc
        creds = service_account.Credentials.from_service_account_file(
            self._creds_path, scopes=_SCOPES
        ).with_subject(self._sender)
        self._svc = build("gmail", "v1", credentials=creds, cache_discovery=False)
        return self._svc

    def send(self, message: EmailMessage) -> SendResult:
        sender = self._resolve_sender(message, self._sender)
        mime = build_mime(message, sender)
        raw = base64.urlsafe_b64encode(mime.as_bytes()).decode("ascii")
        svc = self._service()
        try:
            sent = (
                svc.users()
                .messages()
                .send(userId=sender, body={"raw": raw})
                .execute()
            )
        except Exception as exc:  # noqa: BLE001 - surface as EmailError
            raise EmailError(f"gmail send failed: {exc}") from exc
        return SendResult(
            driver=self.name,
            sent=True,
            recipients=message.recipients,
            message_id=sent.get("id"),
        )
