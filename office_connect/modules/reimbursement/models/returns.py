"""Return-reason taxonomy (seeded) + append-only return events (the learning loop).

A return always carries ≥1 taxonomy reason (COA audit trail). ``reimb_return_events`` is
append-only (``created_*`` only; the migration REVOKEs UPDATE). It is **audited** — it is
a module table, and core cannot import module models into ``_UNAUDITED``, so every insert
hash-chains (which is exactly what we want for a return record).
"""

from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Index, Text, text, TIMESTAMP
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from office_connect.core.base import (
    AuditColsMixin,
    Base,
    LookupMixin,
    PKMixin,
    SoftDeleteMixin,
)
from office_connect.modules.reimbursement.models.enums import (
    ReturnReasonCategory,
    ReturnTarget,
)


class ReimbReturnReasonCatalog(
    PKMixin, AuditColsMixin, SoftDeleteMixin, LookupMixin, Base
):
    __tablename__ = "reimb_return_reason_catalogs"
    __table_args__ = (
        Index(
            "uq_reimb_return_reason_catalogs_code",
            "code",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    code: Mapped[str]
    label: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(ReturnReasonCategory)
    # If true, this reason can be "promoted to a pre-check" (R-8 learning loop).
    promoted_check: Mapped[bool] = mapped_column(server_default=text("false"))


class ReimbReturnEvent(PKMixin, Base):
    """Append-only: one row per return. ``created_*`` only + REVOKE UPDATE."""

    __tablename__ = "reimb_return_events"
    __table_args__ = (
        Index("ix_reimb_return_events_claim_id", "claim_id"),
        Index("ix_reimb_return_events_step_id", "step_id"),
    )

    claim_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("reimb_claims.id"))
    # The workflow step returned from (module → core FK; nullable for a claim-level return).
    step_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("core_workflow_steps.id")
    )
    reason_ids: Mapped[list[Any]] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )  # ≥1 reimb_return_reason_catalogs id (enforced in the service layer)
    free_comment: Mapped[str | None] = mapped_column(Text)
    returned_to: Mapped[str] = mapped_column(ReturnTarget, server_default="claimant")
    created_at: Mapped[Any] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("core_users.id")
    )
