"""Per-user notification delivery preferences (Stage B / Increment 4).

Backs the notifications core-service opt-out model (master-plan §1.1 #4,
"per-user prefs"). One row per ``(user, channel, module)``: ``module IS NULL`` is
the user's default for that channel, a set ``module`` overrides it for that
module's notifications. ``enabled=false`` = opted out (the outbox row is persisted
with ``status='suppressed'`` and never dispatched).

Opt-outs are **not** honored for security/transactional notifications
(``meta['notification_class']`` in ``{'security','transactional'}``) — a user can
never silence a password-reset / MFA mail. That bypass lives in
``core/notifications/recipients.py``, not here.

Uniqueness uses ``NULLS NOT DISTINCT`` (Postgres 16) so the ``module IS NULL``
default row is unique per ``(user, channel)`` too (mirrors ``core_user_roles``).
"""

from sqlalchemy import BigInteger, ForeignKey, Index, text, true
from sqlalchemy.orm import Mapped, mapped_column

from office_connect.core.base import (
    AuditColsMixin,
    Base,
    PKMixin,
    SoftDeleteMixin,
)
from office_connect.core.models.notification import NotificationChannel


class NotificationPreference(PKMixin, AuditColsMixin, SoftDeleteMixin, Base):
    """A user's opt-out choice for a delivery channel (optionally per module)."""

    __tablename__ = "core_notification_preferences"
    __table_args__ = (
        Index(
            "uq_core_notification_preferences_scope",
            "user_id",
            "channel",
            "module",
            unique=True,
            postgresql_nulls_not_distinct=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_core_notification_preferences_user_id", "user_id"),
    )

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("core_users.id"))
    channel: Mapped[str] = mapped_column(NotificationChannel)
    # NULL = the default for this channel; a set value scopes the pref to a module.
    module: Mapped[str | None]
    # Opt-out model: default enabled; a row with enabled=false suppresses delivery.
    enabled: Mapped[bool] = mapped_column(server_default=true())
