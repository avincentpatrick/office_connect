"""Cash advances — the 30-day liquidation clock + the PD 1445 §89 hard-block.

``date_return`` drives the 30-day liquidation deadline (COA 97-002). The **CA hard-block**
(no new travel CA while one is unliquidated) is enforced as a DB constraint — a partial
unique index allowing at most one non-settled CA per claimant — NOT a workflow guard, so
the Chief-Accountant "no unliquidated CA" certification can never be false.

``deadline_date``/``deadline_basis`` (R-6-clock, migration ``0019``) are a **pinned
computed snapshot**, not a derived read: the daily reminder sweep range-queries the
date without loading the config pack per row, and — the real reason — the deadline a
traveller was *told* must not silently move when an admin edits ``liquidation.deadline``
or a holiday is added to the calendar. Only ``services/cash_advance.py`` writes them,
and only when ``date_return`` moves (the same discipline ``reimb_claims.status`` and
``totals`` already follow).
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Date, ForeignKey, Index, Numeric, TIMESTAMP, text
from sqlalchemy.orm import Mapped, mapped_column

from office_connect.core.base import AuditColsMixin, Base, PKMixin, SoftDeleteMixin
from office_connect.modules.reimbursement.models.enums import CashAdvanceStatus


class ReimbCashAdvance(PKMixin, AuditColsMixin, SoftDeleteMixin, Base):
    __tablename__ = "reimb_cash_advances"
    __table_args__ = (
        Index("ix_reimb_cash_advances_claimant_id", "claimant_id"),
        Index("ix_reimb_cash_advances_status", "status"),
        Index("ix_reimb_cash_advances_date_return", "date_return"),
        # The reminder sweep's work-list predicate (status + deadline window).
        Index("ix_reimb_cash_advances_deadline_date", "deadline_date"),
        # CA hard-block (PD 1445 §89): at most ONE unliquidated CA per claimant.
        Index(
            "uq_reimb_cash_advances_open_per_claimant",
            "claimant_id",
            unique=True,
            postgresql_where=text(
                "status IN ('open', 'liquidation_started', 'overdue') "
                "AND deleted_at IS NULL"
            ),
        ),
    )

    claimant_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("core_staff.id"))
    dv_no: Mapped[str | None]
    dv_date: Mapped[date | None] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    dpo_no: Mapped[str | None]
    date_return: Mapped[date | None] = mapped_column(Date)  # drives the 30-day clock
    # The liquidation deadline as computed and PINNED at the moment date_return was
    # last set. NULL until a return date exists — an advance for a trip that has not
    # happened yet has no clock, and a zero-date would be a lie the UI would render.
    deadline_date: Mapped[date | None] = mapped_column(Date)
    # 'calendar' | 'working' — which rule produced deadline_date. Pinned with the
    # date so a later config flip cannot retroactively re-explain an existing
    # deadline. Plain varchar, matching the reimb_claims.status precedent: the legal
    # set is code (services/deadline.py), not DDL, and a PG enum would demand a
    # migration the day DOH practice is confirmed.
    deadline_basis: Mapped[str | None]
    status: Mapped[str] = mapped_column(CashAdvanceStatus, server_default="open")
    settled_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
