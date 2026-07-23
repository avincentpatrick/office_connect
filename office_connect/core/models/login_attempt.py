"""Login-attempt log — append-only auth telemetry (Stage B / Phase 2).

Every authentication attempt lands here: success, failure, throttle, MFA step.
It backs the throttle counters and answers "who tried to get into the Director's
account". Append-only (``created_at`` only, REVOKE UPDATE, unaudited — it IS a
log, like ``core_query_logs``).

Anti-enumeration: ``user_id`` is NULL when the typed identifier matched no
account; ``attempted_identifier`` records what was typed. ``failure_reason`` is a
COARSE machine reason — **never the password**, never a session token
(``session_id_hash`` stores only a hash of the issued id).
"""

from datetime import datetime

from sqlalchemy import BigInteger, Enum, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from office_connect.core.base import Base, PKMixin

LoginOutcome = Enum(
    "success",
    "failure",
    "throttled",
    "mfa_required",
    "mfa_failure",
    name="core_login_outcome",
)


class LoginAttempt(PKMixin, Base):
    """Append-only: created_at only, REVOKE UPDATE, never audited."""

    __tablename__ = "core_login_attempts"
    __table_args__ = (
        Index("ix_core_login_attempts_user_id", "user_id"),
        Index("ix_core_login_attempts_created_at", "created_at"),
        Index("ix_core_login_attempts_outcome", "outcome"),
        Index(
            "ix_core_login_attempts_attempted_identifier",
            "attempted_identifier",
            "created_at",
        ),
    )

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("core_users.id")
    )
    attempted_identifier: Mapped[str]
    outcome: Mapped[str] = mapped_column(LoginOutcome)
    failure_reason: Mapped[str | None]
    ip_address: Mapped[str | None]
    user_agent: Mapped[str | None] = mapped_column(Text)
    session_id_hash: Mapped[str | None]
