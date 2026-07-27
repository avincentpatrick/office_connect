"""Recipient resolution + delivery-preference honoring (Stage B / Increment 4).

The Increment-4 outbox took the recipient verbatim; this closes that seam.
``resolve_recipient`` runs inside ``persist_notification`` (so ``send_notification``'s
public signature is untouched) and answers two questions before the row is written:

1. **Who** — if the caller passed only ``meta['recipient_user_id']`` (no address),
   resolve the login's ``core_users.email`` (falling back to the linked
   ``core_staff.email``). An explicit address always wins.
2. **Whether** — honor per-user opt-outs (``core_notification_preferences``): a
   ``module``-specific row overrides the channel default. ``enabled=false`` →
   ``status='suppressed'`` (persisted for audit, never dispatched). Absence of a row
   = enabled (opt-out model). **Security/transactional** notifications
   (``meta['notification_class']``) bypass prefs entirely — a user can never silence
   a password-reset / MFA mail.

An email-channel notification addressed only by a user id that can't be resolved
(soft-deleted/absent user, no address) is ``suppressed`` rather than dead-lettered.

Pure core: queries ``core_users`` / ``core_staff`` / ``core_notification_preferences``
through the caller's session (the global soft-delete filter applies); no ops import.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.config import Settings, get_settings
from office_connect.core.models.notification_preference import NotificationPreference
from office_connect.core.models.staff import Staff
from office_connect.core.models.user import User

# Notification classes that ignore opt-outs (a user cannot silence these).
_PREFS_BYPASS_CLASSES = frozenset({"security", "transactional"})


@dataclass(frozen=True)
class Resolved:
    recipient_email: str | None
    recipient_user_id: int | None
    status: str  # "queued" | "suppressed"


async def resolve_recipient(
    session: AsyncSession, notification, *, settings: Settings | None = None
) -> Resolved:
    settings = settings or get_settings()
    meta = notification.meta or {}
    email = notification.email

    recipient_email = (
        email.to[0] if (email and email.to) else meta.get("recipient_email")
    )
    recipient_user_id = meta.get("recipient_user_id")

    user: User | None = None
    if recipient_user_id is not None:
        user = (
            await session.execute(select(User).where(User.id == recipient_user_id))
        ).scalar_one_or_none()
        if recipient_email is None and user is not None:
            recipient_email = user.email
            if not recipient_email and user.staff_id is not None:
                staff = (
                    await session.execute(
                        select(Staff).where(Staff.id == user.staff_id)
                    )
                ).scalar_one_or_none()
                if staff is not None:
                    recipient_email = staff.email

    status = "queued"

    # Opt-out honoring — only when we know the user and the class is not mandatory.
    notification_class = meta.get("notification_class", "operational")
    if (
        recipient_user_id is not None
        and user is not None
        and notification_class not in _PREFS_BYPASS_CLASSES
    ):
        if not await _channel_enabled(
            session,
            user_id=recipient_user_id,
            channel=notification.channel,
            module=meta.get("module"),
        ):
            status = "suppressed"

    # Email addressed by user id but unresolvable → suppress (never dead-letter).
    if (
        status == "queued"
        and notification.channel == "email"
        and recipient_email is None
        and recipient_user_id is not None
    ):
        status = "suppressed"

    return Resolved(
        recipient_email=recipient_email,
        recipient_user_id=recipient_user_id,
        status=status,
    )


async def _channel_enabled(
    session: AsyncSession, *, user_id: int, channel: str, module: str | None
) -> bool:
    """Effective opt-in for (user, channel): a module-specific row overrides the
    channel default (``module IS NULL``); no row = enabled."""
    rows = (
        (
            await session.execute(
                select(NotificationPreference).where(
                    NotificationPreference.user_id == user_id,
                    NotificationPreference.channel == channel,
                )
            )
        )
        .scalars()
        .all()
    )
    chosen = next((r for r in rows if r.module == module), None)
    if chosen is None:
        chosen = next((r for r in rows if r.module is None), None)
    return True if chosen is None else chosen.enabled
