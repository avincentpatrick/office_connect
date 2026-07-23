"""Log email driver — the dev fail-safe.

Records the message to the ``office_connect.email`` logger instead of delivering
it. Selected automatically when no transport is configured, so a fresh dev stack
never needs an SMTP server to exercise the notification path. Never used when
``APP_ENV=production`` unless explicitly set (auto-selection prefers SMTP).
"""

from __future__ import annotations

import logging

from office_connect.core.email.base import EmailDriver, EmailMessage, SendResult

logger = logging.getLogger("office_connect.email")


class LogEmailDriver(EmailDriver):
    name = "log"

    def send(self, message: EmailMessage) -> SendResult:
        logger.info(
            "email (not sent — log driver): to=%s subject=%r sender=%s\n%s",
            ", ".join(message.recipients),
            message.subject,
            message.sender or "(default)",
            message.text_body,
        )
        return SendResult(driver=self.name, sent=False, recipients=message.recipients)
