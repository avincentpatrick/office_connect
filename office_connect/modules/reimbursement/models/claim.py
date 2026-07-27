"""The claim header + itinerary legs — the heart of the reimbursement schema.

``reimb_claims`` is the parent (a reimbursement OR a liquidation, by ``kind``).
Connectedness (master-plan §1.2/§1.3): ``activity_id`` links the spine, and
``workflow_instance_id`` FKs INTO the shared engine (`core_workflow_instances`) — the
approval chain is the engine, not a module runtime table. ``totals`` is server-computed
(R-2); ``status`` is a denormalized read-model synced from the workflow instance.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, Date, ForeignKey, Index, Integer, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from office_connect.core.base import AuditColsMixin, Base, PKMixin, SoftDeleteMixin
from office_connect.modules.reimbursement.models.enums import (
    ClaimKind,
    FundSource,
    HolderKind,
    TransportMode,
)


class ReimbClaim(PKMixin, AuditColsMixin, SoftDeleteMixin, Base):
    __tablename__ = "reimb_claims"
    __table_args__ = (
        # ref_no unique among LIVE rows; a soft-deleted number is never reissued by
        # the allocator, so this partial index only guards live collisions.
        Index(
            "uq_reimb_claims_ref_no",
            "ref_no",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_reimb_claims_claimant_id", "claimant_id"),
        Index("ix_reimb_claims_activity_id", "activity_id"),
        Index("ix_reimb_claims_workflow_instance_id", "workflow_instance_id"),
        Index("ix_reimb_claims_cash_advance_id", "cash_advance_id"),
        Index("ix_reimb_claims_status", "status"),
        Index("ix_reimb_claims_kind", "kind"),
    )

    ref_no: Mapped[str | None]  # RB-YYYY-NNNN / LQ-YYYY-NNNN (allocated at submit)
    kind: Mapped[str] = mapped_column(ClaimKind)
    claimant_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("core_staff.id"))
    activity_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("core_activities.id")
    )
    # The approval chain lives in the shared engine (module → core, never reverse).
    workflow_instance_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("core_workflow_instances.id")
    )
    dpo_no: Mapped[str | None]
    dpo_date: Mapped[date | None] = mapped_column(Date)
    # Soft reference to a DTWIS document (no FK — DTWIS ships at Stage E; backfilled).
    dpo_document_id: Mapped[int | None] = mapped_column(BigInteger)
    purpose: Mapped[str | None] = mapped_column(Text)
    destination: Mapped[str | None] = mapped_column(Text)
    # PSGC region of the destination → EO 77 cluster (replaces destination_class).
    destination_region_code: Mapped[str | None]
    date_depart: Mapped[date | None] = mapped_column(Date)
    date_return: Mapped[date | None] = mapped_column(Date)
    # EO 77 50-km attestations (claimant-asserted — core_staff has no official-station
    # field to derive distance from). Within 50 km WITHOUT an overnight stay, the
    # engine pays transport fare only: 0% DTE (research digest supersedes spec §8's
    # lodging-only strip; see the module delta register). Radius value stays config
    # (`per_diem.radius_km`).
    is_within_50km: Mapped[bool] = mapped_column(server_default=text("false"))
    overnight_stay: Mapped[bool] = mapped_column(server_default=text("false"))
    fund_source: Mapped[str | None] = mapped_column(FundSource)
    is_jo_cos: Mapped[bool] = mapped_column(server_default=text("false"))
    cash_advance_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("reimb_cash_advances.id")
    )
    # Denormalized read-model of the workflow current state (synced at R-4-app).
    status: Mapped[str | None]
    holder_kind: Mapped[str | None] = mapped_column(HolderKind)
    holder_id: Mapped[int | None] = mapped_column(BigInteger)  # polymorphic, no FK
    holder_since: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    next_action: Mapped[str | None] = mapped_column(Text)
    liquidation_deadline: Mapped[date | None] = mapped_column(Date)
    totals: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb")
    )
    custom: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb")
    )


class ReimbItineraryLeg(PKMixin, AuditColsMixin, SoftDeleteMixin, Base):
    """Per-leg itinerary row (child of a claim). ``per_diem_pct`` (100/50/0) and the
    computed amounts are populated by the R-2 per-diem engine, not here."""

    __tablename__ = "reimb_itinerary_legs"
    __table_args__ = (Index("ix_reimb_itinerary_legs_claim_id", "claim_id"),)

    claim_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("reimb_claims.id"))
    seq: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    leg_date: Mapped[date | None] = mapped_column(Date)
    place: Mapped[str | None] = mapped_column(Text)
    destination_region_code: Mapped[str | None]  # per-leg cluster routing
    time_depart: Mapped[str | None]  # "HH:MM"
    time_arrive: Mapped[str | None]
    transport_mode: Mapped[str | None] = mapped_column(TransportMode)
    fare: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    per_diem_pct: Mapped[int | None] = mapped_column(Integer)  # 100 / 50 / 0
    per_diem_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    leg_total: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    # Host-provided deductions (EO 77): strip 50% lodging / 30% meals for that day.
    lodging_provided: Mapped[bool] = mapped_column(server_default=text("false"))
    meals_provided: Mapped[bool] = mapped_column(server_default=text("false"))
