"""Auth accounts — ``core_users`` (Stage B / Phase 2, core-service #14).

The identity every ``*_by`` / ``actor_id`` column FKs to (the deferred-FK closure
in migration 0010). Split-model (foundation.md §5): a login OPTIONALLY references
a ``core_staff`` person via ``staff_id`` (NULL for break-glass / system accounts).

Provisioning is admin-only — there is NO self-registration (auth-rbac-onprem.md).
Offboarding is ``is_active=false`` + session revocation (Stage B/B2), never a hard
delete, so audit attribution survives.

``password_hash`` and ``mfa_secret`` are SPI and are **excluded from the audit
payload** (``__audit_exclude__``): the hash chain is immutable, so a secret
written into it could never be redacted (master-plan §4 #4; database-standards §7).
The field NAME still appears in the payload (so "password changed" is auditable),
only the VALUE is withheld.
"""

from datetime import datetime

from sqlalchemy import BigInteger, Enum, ForeignKey, Index, Integer, false, text, true
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from office_connect.core.base import (
    AuditColsMixin,
    Base,
    PKMixin,
    SoftDeleteMixin,
)

AuthSource = Enum("local", "ldap", name="core_auth_source")


class User(PKMixin, AuditColsMixin, SoftDeleteMixin, Base):
    """A login account. Business table (explicit ``is_active`` — not a lookup)."""

    # Columns whose VALUES never enter the immutable audit chain (SPI/secrets).
    __audit_exclude__ = frozenset({"password_hash", "mfa_secret"})

    __tablename__ = "core_users"
    __table_args__ = (
        Index(
            "uq_core_users_email",
            "email",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        # At most one live account per staff person.
        Index(
            "uq_core_users_staff_id",
            "staff_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND staff_id IS NOT NULL"),
        ),
        Index("ix_core_users_is_active", "is_active"),
        Index("ix_core_users_staff_id", "staff_id"),
    )

    email: Mapped[str]
    password_hash: Mapped[str | None]
    must_change_password: Mapped[bool] = mapped_column(server_default=false())
    password_changed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True)
    )
    mfa_enabled: Mapped[bool] = mapped_column(server_default=false())
    mfa_secret: Mapped[str | None]
    is_active: Mapped[bool] = mapped_column(server_default=true())
    # Break-glass local admin, excluded from the future LDAP path (auth-rbac §).
    is_break_glass: Mapped[bool] = mapped_column(server_default=false())
    auth_source: Mapped[str] = mapped_column(AuthSource, server_default="local")
    # Bumped on any role grant/revoke to invalidate the Redis permission cache (B3).
    permissions_version: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    last_login_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    staff_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("core_staff.id")
    )
