"""Email drivers (transport for core-service #4 Notifications).

``get_email_driver()`` returns the configured driver. When ``EMAIL_DRIVER`` is
unset the choice is automatic: ``smtp`` if ``SMTP_HOST`` is configured, else
``log`` (the dev fail-safe that records instead of sending). Explicit values:
``smtp`` | ``gmail`` | ``log``.
"""

from __future__ import annotations

from office_connect.core.config import Settings, get_settings
from office_connect.core.email.base import (
    EmailDriver,
    EmailError,
    EmailMessage,
    SendResult,
)

__all__ = [
    "EmailDriver",
    "EmailError",
    "EmailMessage",
    "SendResult",
    "get_email_driver",
    "resolve_email_driver_name",
]


def resolve_email_driver_name(settings: Settings) -> str:
    """The driver name after auto-selection (does not build the driver)."""
    explicit = (settings.email_driver or "").strip().lower()
    if explicit:
        return explicit
    return "smtp" if settings.smtp_host else "log"


def get_email_driver(settings: Settings | None = None) -> EmailDriver:
    settings = settings or get_settings()
    name = resolve_email_driver_name(settings)
    if name == "smtp":
        from office_connect.core.email.smtp import SMTPEmailDriver

        return SMTPEmailDriver(settings)
    if name == "gmail":
        from office_connect.core.email.gmail import GmailEmailDriver

        return GmailEmailDriver(settings)
    if name == "log":
        from office_connect.core.email.log import LogEmailDriver

        return LogEmailDriver()
    raise EmailError(f"unknown email_driver {settings.email_driver!r}")
