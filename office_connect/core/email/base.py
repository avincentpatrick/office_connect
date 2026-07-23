"""Email driver interface (transport layer of core-service #4 Notifications).

Two real drivers — SMTP (stdlib, the on-prem default) and Gmail API — plus a
``log`` driver that records the message instead of sending (the dev fail-safe
when no transport is configured). Callers build an :class:`EmailMessage` and
hand it to a driver's ``send``; the notification outbox (``core/notifications``)
selects the driver. Modules never construct a driver directly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class EmailError(RuntimeError):
    """Raised for any email-driver failure (config, connection, or send)."""


@dataclass
class EmailMessage:
    """A single outbound email. ``sender`` may be None → the driver's default."""

    to: list[str]
    subject: str
    text_body: str
    html_body: str | None = None
    sender: str | None = None
    cc: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Accept a bare string for convenience; normalize to a list.
        if isinstance(self.to, str):
            self.to = [self.to]
        if isinstance(self.cc, str):
            self.cc = [self.cc]
        if not self.to:
            raise EmailError("email has no recipients")
        if not self.subject:
            raise EmailError("email has no subject")

    @property
    def recipients(self) -> list[str]:
        return [*self.to, *self.cc]


@dataclass(frozen=True)
class SendResult:
    """Outcome of a send. ``message_id`` is set when the transport returns one;
    ``sent`` is False for the log driver (recorded, not delivered)."""

    driver: str
    sent: bool
    recipients: list[str]
    message_id: str | None = None


class EmailDriver(ABC):
    """Import-safe: build any remote client lazily so importing needs no creds."""

    name: str = "base"

    @abstractmethod
    def send(self, message: EmailMessage) -> SendResult:
        """Deliver ``message``. Raises :class:`EmailError` on failure."""

    def _resolve_sender(self, message: EmailMessage, default: str | None) -> str:
        sender = message.sender or default
        if not sender:
            raise EmailError(
                f"{self.name} email needs a sender (message.sender or a "
                "configured default: SMTP_FROM / GMAIL_SENDER)"
            )
        return sender
