"""Attachments join + append-only tracking logs (status history, external FMS events).

``reimb_attachments`` is a thin join to the core attachments service (Rule 10 — the
module never re-implements validation/scan/store): it carries the physical-custody state
and the GRDS-2023 retention class. ``reimb_status_histories`` and ``reimb_external_events``
are append-only (``created_*`` only + REVOKE UPDATE) and feed the tracker UI; both are
audited (module tables can't be added to core's ``_UNAUDITED``, and hash-chaining them is
desirable).
"""

from datetime import date
from typing import Any

from sqlalchemy import BigInteger, Date, ForeignKey, Index, Text, text, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from office_connect.core.base import AuditColsMixin, Base, PKMixin, SoftDeleteMixin
from office_connect.modules.reimbursement.models.enums import AttachmentCustody


class ReimbAttachment(PKMixin, AuditColsMixin, SoftDeleteMixin, Base):
    """Join a claim to a core attachment + custody/retention (rides core attachments)."""

    __tablename__ = "reimb_attachments"
    __table_args__ = (
        Index("ix_reimb_attachments_claim_id", "claim_id"),
        Index("ix_reimb_attachments_attachment_id", "attachment_id"),
        Index("ix_reimb_attachments_checklist_item_id", "checklist_item_id"),
    )

    claim_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("reimb_claims.id"))
    attachment_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("core_attachments.id")
    )
    checklist_item_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("reimb_checklist_items.id")
    )
    custody: Mapped[str] = mapped_column(AttachmentCustody, server_default="scanned")
    retention_class: Mapped[str] = mapped_column(server_default="financial_10yr")
    notes: Mapped[str | None] = mapped_column(Text)


class ReimbStatusHistory(PKMixin, Base):
    """Append-only transition log feeding the tracker UI. created_* only, REVOKE UPDATE."""

    __tablename__ = "reimb_status_histories"
    __table_args__ = (Index("ix_reimb_status_histories_claim_id", "claim_id"),)

    claim_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("reimb_claims.id"))
    from_status: Mapped[str | None]
    to_status: Mapped[str]
    actor_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("core_users.id")
    )
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[Any] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("core_users.id")
    )


class ReimbExternalEvent(PKMixin, Base):
    """Append-only FMS journey updates (With Budget / Accounting / Payment). REVOKE UPDATE."""

    __tablename__ = "reimb_external_events"
    __table_args__ = (Index("ix_reimb_external_events_claim_id", "claim_id"),)

    claim_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("reimb_claims.id"))
    status: Mapped[str]
    noted_by: Mapped[str | None]
    note: Mapped[str | None] = mapped_column(Text)
    event_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[Any] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("core_users.id")
    )
