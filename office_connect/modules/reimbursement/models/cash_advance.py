"""Cash advances — the 30-day liquidation clock + the PD 1445 §89 hard-block.

``date_return`` drives the 30-day liquidation deadline (COA 97-002). The **CA hard-block**
(no new travel CA while one is unliquidated) is enforced as a DB constraint — a partial
unique index allowing at most one non-settled CA per claimant — NOT a workflow guard, so
the Chief-Accountant "no unliquidated CA" certification can never be false.
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
    status: Mapped[str] = mapped_column(CashAdvanceStatus, server_default="open")
    settled_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
