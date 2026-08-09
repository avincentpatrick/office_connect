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
        # Stage D-2 (migration 0024): the calendar's travel source filters on a
        # date window, and `date_depart` is the leading, sargable half of that
        # predicate. Nothing queried claims BY TRIP DATE before — the queue and
        # the board both order on `holder_since`.
        Index("ix_reimb_claims_date_depart", "date_depart"),
        Index("ix_reimb_claims_workflow_instance_id", "workflow_instance_id"),
        # One live instance per claim (R-4-app): the submit service's claim-row
        # lock is the race fix; this is the DB belt behind it (migration 0015).
        Index(
            "uq_reimb_claims_workflow_instance_id",
            "workflow_instance_id",
            unique=True,
            postgresql_where=text("workflow_instance_id IS NOT NULL"),
        ),
        Index("ix_reimb_claims_cash_advance_id", "cash_advance_id"),
        Index("ix_reimb_claims_status", "status"),
        Index("ix_reimb_claims_kind", "kind"),
        Index("ix_reimb_claims_spawned_from_claim_id", "spawned_from_claim_id"),
        # One live "Reimbursement Due" spawn per liquidation (R-6-liq-settle,
        # migration 0020). `cancelled` excluded so a mistaken spawn can be
        # cancelled and re-taken — the same exclusion liquidation.LIVE_STATUSES
        # makes for the same reason.
        Index(
            "uq_reimb_claims_spawn_per_liquidation",
            "spawned_from_claim_id",
            unique=True,
            postgresql_where=text(
                "spawned_from_claim_id IS NOT NULL "
                "AND status IS DISTINCT FROM 'cancelled' AND deleted_at IS NULL"
            ),
        ),
        # One live liquidation per cash advance (migration 0020) — the DB belt
        # behind start_liquidation's `SELECT … FOR UPDATE`, deferred from
        # R-6-liq-chain exactly as 0015 followed R-4-app's row lock.
        # `IS DISTINCT FROM` rather than `<>` because `status` is nullable and
        # `<>` is NULL-for-NULL, which would drop un-stamped rows out of the
        # index — precisely where a duplicate would hide.
        Index(
            "uq_reimb_claims_live_liquidation_per_advance",
            "cash_advance_id",
            unique=True,
            postgresql_where=text(
                "kind = 'liquidation' AND cash_advance_id IS NOT NULL "
                "AND status IS DISTINCT FROM 'cancelled' AND deleted_at IS NULL"
            ),
        ),
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
    # Spec §6.2's "Reimbursement Due" side-step made durable (R-6-liq-settle):
    # the reimbursement of the difference points back at the liquidation that
    # produced it, so neither document can be read without the other. NULL on
    # every claim a traveller filed for themselves.
    spawned_from_claim_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("reimb_claims.id")
    )
    # "Other expenses" total (spec §9.3 step 3) — persisted so resubmit recomputes
    # with it instead of silently resetting to zero (migration 0016). Itemized
    # expense lines arrive with the R-3 checklist engine.
    other_total: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), server_default=text("0")
    )
    # Spec §6.1 row 8's "admin records payout ref" (R-7-events, migration 0021).
    # `payout_ref` is what FMS hands back (ADA/LDDAP reference, check number) and
    # is deliberately NOT unique — one LDDAP-ADA pays many vouchers at once.
    # `paid_on` is the date the money moved, not the moment somebody typed it in
    # (that is `updated_at` + the status-history row). `paid_by` is a real column
    # for the same reason `settled_by` is: who closed a financial record is a
    # fact OF the record (rule 5).
    payout_ref: Mapped[str | None]
    paid_on: Mapped[date | None] = mapped_column(Date)
    paid_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("core_users.id")
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
