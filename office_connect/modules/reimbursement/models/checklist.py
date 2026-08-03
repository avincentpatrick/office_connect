"""Documentary-requirements checklist — catalog (seeded) + per-claim instances.

The catalog is seeded at R-1 (pinned to COA Circular 2023-004); the ``required_rule`` /
``auto_checks`` GRAMMAR that interprets these JSONB rules is built as a **core** service
at R-3 (Rule 10 — reimbursement is its first consumer). R-1 lands the tables + seed data
only.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, Text, text, TIMESTAMP
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from office_connect.core.base import (
    AuditColsMixin,
    Base,
    LookupMixin,
    PKMixin,
    SoftDeleteMixin,
)
from office_connect.modules.reimbursement.models.enums import (
    ChecklistEvidence,
    ChecklistGroup,
    ChecklistItemStatus,
)


class ReimbChecklistCatalog(PKMixin, AuditColsMixin, SoftDeleteMixin, LookupMixin, Base):
    __tablename__ = "reimb_checklist_catalogs"
    __table_args__ = (
        Index(
            "uq_reimb_checklist_catalogs_kind_code",
            "claim_kind",
            "code",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_reimb_checklist_catalogs_group", "group"),
    )

    claim_kind: Mapped[str | None]  # "reimbursement" | "liquidation" | NULL (both)
    code: Mapped[str]  # e.g. "LR-06"
    label: Mapped[str] = mapped_column(Text)  # verbatim checklist wording
    group: Mapped[str] = mapped_column(ChecklistGroup)
    required_rule: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb")
    )
    auto_checks: Mapped[list[Any]] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )
    evidence: Mapped[str] = mapped_column(ChecklistEvidence)
    circular_version: Mapped[str | None]  # e.g. "COA Circular 2023-004"
    sort: Mapped[int] = mapped_column(Integer, server_default=text("0"))


class ReimbChecklistItem(PKMixin, AuditColsMixin, SoftDeleteMixin, Base):
    __tablename__ = "reimb_checklist_items"
    __table_args__ = (
        Index("ix_reimb_checklist_items_claim_id", "claim_id"),
        Index("ix_reimb_checklist_items_catalog_id", "catalog_id"),
        # At most ONE live item per (claim, catalog row) — the invariant the
        # engine's reconciliation assumes. The claim's FOR UPDATE lock is the
        # app-level serializer; this is the DB belt behind it (0017, same
        # pattern as 0015's claim↔instance index).
        Index(
            "uq_reimb_checklist_items_claim_catalog",
            "claim_id",
            "catalog_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    claim_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("reimb_claims.id"))
    catalog_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("reimb_checklist_catalogs.id")
    )
    status: Mapped[str] = mapped_column(ChecklistItemStatus, server_default="missing")
    # Which circular revision this item was materialized against (0017).
    # master-plan §1.1 #7 requires catalog versions pinned to the issuing
    # revision, and `apply_dataset` upserts catalog rows IN PLACE — without a
    # snapshot here, revising a catalog row retroactively rewrites what a
    # historical claim's item meant. Unbackfillable after the fact.
    circular_version: Mapped[str | None]
    # DISPLAY MIRROR ONLY. `reimb_attachments` is the source of truth (it has the
    # FK, the soft-delete columns and the custody state); db-standards §11 forbids
    # putting anything other code must join on inside JSONB. Reassign this list,
    # never mutate it in place — the column has no MutableList.
    attachment_ids: Mapped[list[Any]] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )
    waiver_reason: Mapped[str | None] = mapped_column(Text)
    checked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    checked_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("core_users.id")
    )
