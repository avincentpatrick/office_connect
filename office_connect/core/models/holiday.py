"""PH holiday & work-suspension calendar — the data behind the working-day engine.

Master-plan §1.1 #6. National regular/special holidays plus "walang pasok" work
suspensions, per year. ``core/workdays.py`` reads the non-working rows here to do
every deadline's math. Refreshed annually from the holiday proclamations (seed
framework owner/cadence — Group G).
"""

from datetime import date

from sqlalchemy import Date, Enum, Index, text
from sqlalchemy.orm import Mapped, mapped_column

from office_connect.core.base import (
    AuditColsMixin,
    Base,
    LookupMixin,
    PKMixin,
    SoftDeleteMixin,
)

HolidayType = Enum(
    "regular",
    "special_non_working",
    "special_working",
    "work_suspension",
    "local",
    name="core_holiday_type",
)

HolidayScope = Enum("national", "local", name="core_holiday_scope")


class Holiday(PKMixin, AuditColsMixin, SoftDeleteMixin, LookupMixin, Base):
    __tablename__ = "core_holidays"
    __table_args__ = (
        Index("ix_core_holidays_calendar_date", "calendar_date"),
        Index("ix_core_holidays_holiday_type", "holiday_type"),
        # A live (date, name, scope) is unique; a soft-deleted one never blocks re-entry.
        Index(
            "uq_core_holidays_date_name_scope",
            "calendar_date",
            "name",
            "scope",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    calendar_date: Mapped[date] = mapped_column(Date)
    name: Mapped[str]
    holiday_type: Mapped[str] = mapped_column(HolidayType)
    scope: Mapped[str] = mapped_column(HolidayScope, server_default="national")
    locality: Mapped[str | None]  # set when scope='local'
    proclamation_ref: Mapped[str | None]
