"""Activity registry — the cross-module join key (Blueprint §2.2, Day-1 #15).

"What work was this for?" — claims, surveys, bookings, and documents all point
here via a nullable ``activity_id``. Creation is deliberately lightweight
(title is the only required user field); an unlinked record is always allowed,
just less reportable.
"""

from datetime import date
from typing import Any

from sqlalchemy import BigInteger, Date, Enum, ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from office_connect.core.base import AuditColsMixin, Base, PKMixin, SoftDeleteMixin

ActivityStatus = Enum(
    "planned", "ongoing", "done", "cancelled", name="core_activity_status"
)


class Activity(PKMixin, AuditColsMixin, SoftDeleteMixin, Base):
    __tablename__ = "core_activities"
    __table_args__ = (
        Index("ix_core_activities_status", "status"),
        Index("ix_core_activities_date_start", "date_start"),
        Index("ix_core_activities_ppa_code", "ppa_code"),
    )

    title: Mapped[str]
    ppa_code: Mapped[str | None]  # WFP linkage later; free until then
    division_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("core_org_units.id")
    )
    section_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("core_org_units.id")
    )
    date_start: Mapped[date] = mapped_column(Date)
    date_end: Mapped[date | None] = mapped_column(Date)
    venue: Mapped[str | None]
    status: Mapped[str] = mapped_column(ActivityStatus, server_default="planned")
    custom: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb")
    )
