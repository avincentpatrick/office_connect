"""DB-driven feature flags — fail-safe OFF (Day-1 #9; lookup table).

A feature is ON only when ``enabled AND is_active`` on a live row:
``is_active`` retires the flag row itself; ``enabled`` is the flag state.
Anything unreadable is reported OFF by /api/v1/config.
"""

from sqlalchemy import Index, false, text
from sqlalchemy.orm import Mapped, mapped_column

from office_connect.core.base import (
    AuditColsMixin,
    Base,
    LookupMixin,
    PKMixin,
    SoftDeleteMixin,
)


class FeatureFlag(PKMixin, AuditColsMixin, SoftDeleteMixin, LookupMixin, Base):
    __tablename__ = "core_feature_flags"
    __table_args__ = (
        # Partial unique: a soft-deleted flag never blocks re-creating its key
        # (database-standards.md §8).
        Index(
            "uq_core_feature_flags_key",
            "key",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    key: Mapped[str]  # e.g. "module.reimbursement"
    enabled: Mapped[bool] = mapped_column(server_default=false())  # fail-safe OFF
    description: Mapped[str | None]
