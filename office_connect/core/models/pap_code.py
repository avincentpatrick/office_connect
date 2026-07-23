"""UACS / PREXC code spine — the planning↔execution↔reporting tie-out keys.

Master-plan §1.1 #15 + §5 corrections ledger: since FY 2018 the hierarchy is
PREXC (cost structure → organizational outcome → program → subprogram →
activity/project), and UACS codes are **never reused** — a code that changes
meaning is deactivated (``is_active=false``) and a new row added, never
repurposed. Everything is **per-FY** and **effective-dated**.

- ``core_pap_codes`` — the per-FY PREXC tree (self-referential ``parent_id``).
- ``core_object_codes`` — the 10-digit UACS object codes (travel =
  ``5-02-01-010-00``); effective-dated so a revision is a new row, not an edit.

These are skeletons this increment; the year-rollover re-mapping wizard is later.
"""

from datetime import date

from sqlalchemy import BigInteger, Date, Enum, ForeignKey, Index, text
from sqlalchemy.orm import Mapped, mapped_column

from office_connect.core.base import (
    AuditColsMixin,
    Base,
    LookupMixin,
    PKMixin,
    SoftDeleteMixin,
)

PapLevel = Enum(
    "cost_structure",
    "oo",
    "program",
    "subprogram",
    "activity",
    "project",
    name="core_pap_level",
)


class PapCode(PKMixin, AuditColsMixin, SoftDeleteMixin, LookupMixin, Base):
    """One node in a fiscal year's PREXC tree. Deactivate, never reuse a code."""

    __tablename__ = "core_pap_codes"
    __table_args__ = (
        Index(
            "uq_core_pap_codes_fiscal_year_uacs_code",
            "fiscal_year",
            "uacs_code",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_core_pap_codes_fiscal_year", "fiscal_year"),
        Index("ix_core_pap_codes_uacs_code", "uacs_code"),
        Index("ix_core_pap_codes_parent_id", "parent_id"),
        Index("ix_core_pap_codes_level", "level"),
    )

    fiscal_year: Mapped[int]
    uacs_code: Mapped[str]
    level: Mapped[str] = mapped_column(PapLevel)
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("core_pap_codes.id")
    )
    title: Mapped[str]
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)


class ObjectCode(PKMixin, AuditColsMixin, SoftDeleteMixin, LookupMixin, Base):
    """A 10-digit UACS object code (e.g. travel = ``5-02-01-010-00``).

    Effective-dated: a rate/definition revision is a new row with a fresh
    ``effective_from``; the old row is deactivated, never edited in place.
    """

    __tablename__ = "core_object_codes"
    __table_args__ = (
        Index(
            "uq_core_object_codes_code_effective_from",
            "uacs_object_code",
            "effective_from",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_core_object_codes_uacs_object_code", "uacs_object_code"),
    )

    uacs_object_code: Mapped[str]
    title: Mapped[str]
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
