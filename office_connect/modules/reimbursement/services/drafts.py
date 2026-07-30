"""Draft business-field mutation — the wizard's write path BESIDE the lifecycle.

``lifecycle.py`` owns every status/holder/ref/totals-sync write; this module
owns the claim's OWN business fields (trip / itinerary / money inputs) while
the claim is still with the claimant (status draft/returned). It never touches
``status``/``holder_*``/``next_action``/``ref_no`` and never calls the engine.

Stale-money doctrine (R-2-wizard): any change to a compute INPUT clears
``claim.totals`` (and a legs replace also nulls the per-leg computed columns) —
stale money is worse than absent money, and the FE derives the Money step's
task-list state from ``totals``, so clearing re-opens it automatically. The
money step's ``/compute`` rewrites both.

Everything here flushes and never commits — the router owns the transaction
(the module-wide contract shared by ``lifecycle`` and ``compute``).
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.models import Activity
from office_connect.core.money import to_money
from office_connect.core.session import set_audit_context
from office_connect.core.soft_delete import soft_delete
from office_connect.modules.reimbursement.models import (
    ReimbClaim,
    ReimbItineraryLeg,
)
from office_connect.modules.reimbursement.services import errors
from office_connect.modules.reimbursement.services import status as st
from office_connect.modules.reimbursement.services.compute import (
    compute_claim_totals,
)
from office_connect.modules.reimbursement.services.lifecycle import (
    _is_owner,
    _locked_claim,
)

# The claimant-editable business fields (the wizard's PATCH whitelist).
EDITABLE_FIELDS = frozenset(
    {
        "activity_id",
        "dpo_no",
        "dpo_date",
        "purpose",
        "destination",
        "destination_region_code",
        "date_depart",
        "date_return",
        "is_within_50km",
        "overnight_stay",
        "fund_source",
        "other_total",
    }
)

# Changing any of these invalidates a computed snapshot (per-diem inputs +
# the persisted "other" total). purpose/destination/dpo_*/fund_source are
# display-only to the engine and leave a valid snapshot alone.
_COMPUTE_INPUTS = frozenset(
    {
        "date_depart",
        "date_return",
        "destination_region_code",
        "is_within_50km",
        "overnight_stay",
        "other_total",
    }
)

# NOT NULL columns — an explicit JSON null means "no change", never a write.
_NON_NULLABLE = frozenset({"other_total", "is_within_50km", "overnight_stay"})

_LEG_FIELDS = frozenset(
    {
        "leg_date",
        "place",
        "destination_region_code",
        "time_depart",
        "time_arrive",
        "transport_mode",
        "fare",
        "lodging_provided",
        "meals_provided",
    }
)

_EDITABLE_STATUSES = frozenset({st.DRAFT, st.RETURNED})


def _assert_editable(claim: ReimbClaim) -> None:
    """Claimant-held states only (legacy pre-R-2-wizard rows coalesce to
    draft — status stamping began at ``create_draft_claim``)."""
    if (claim.status or st.DRAFT) not in _EDITABLE_STATUSES:
        raise errors.claim_not_editable()


async def _owned_editable_claim(
    session: AsyncSession, *, claim_id: int, actor_user_id: int
) -> ReimbClaim:
    claim = await _locked_claim(session, claim_id)
    # Ownership BEFORE editability: the 409-vs-403 distinction would otherwise
    # hand any staff user (global reimb.claim.create grant) an existence-plus-
    # status oracle over other people's claims (§3.2 — not bureau-public).
    if not await _is_owner(session, claim, actor_user_id):
        raise errors.not_claim_owner()
    _assert_editable(claim)
    return claim


async def update_draft_fields(
    session: AsyncSession,
    *,
    claim_id: int,
    actor_user_id: int,
    changes: Mapping[str, Any],
) -> ReimbClaim:
    """Apply a whitelisted partial update to an owned, claimant-held claim.

    ``changes`` carries only fields the caller actually sent (the router uses
    ``model_dump(exclude_unset=True)``). Raises the ``errors`` factories on
    ownership/state/reference problems; unknown field names are a programmer
    error (the schema is the wire whitelist) and raise ``ValueError``."""
    set_audit_context(session, actor_id=actor_user_id)
    claim = await _owned_editable_claim(
        session, claim_id=claim_id, actor_user_id=actor_user_id
    )

    unknown = set(changes) - EDITABLE_FIELDS
    if unknown:
        raise ValueError(f"non-editable fields: {sorted(unknown)}")

    stale = False
    for field, value in changes.items():
        if value is None and field in _NON_NULLABLE:
            continue
        if field == "other_total":
            value = to_money(value)
            if value < 0:
                raise ValueError("other_total cannot be negative")
        if field == "activity_id" and value is not None:
            activity = (
                await session.execute(select(Activity).where(Activity.id == value))
            ).scalar_one_or_none()
            if activity is None:
                raise errors.unknown_activity(value)
        if getattr(claim, field) != value:
            stale = stale or field in _COMPUTE_INPUTS
            setattr(claim, field, value)

    if (
        claim.date_depart is not None
        and claim.date_return is not None
        and claim.date_return < claim.date_depart
    ):
        raise errors.invalid_trip_dates()

    if stale and claim.totals:
        claim.totals = {}
    await session.flush()
    return claim


async def replace_legs(
    session: AsyncSession,
    *,
    claim_id: int,
    actor_user_id: int,
    legs: Sequence[Mapping[str, Any]],
) -> ReimbClaim:
    """Bulk-replace the itinerary (the wizard edits the whole leg table, one
    atomic PUT). Rows carrying an ``id`` must belong to THIS claim and are
    updated in place; id-less rows are inserted; live legs absent from the
    body are SOFT-deleted (standing rule 6 — never a hard DELETE). ``seq`` is
    reassigned 1..n in body order; the computed columns are nulled on every
    surviving leg and ``claim.totals`` is cleared — ``/compute`` rewrites
    them. A gov-vehicle leg with a fare is stored permissively and fail-closes
    at compute (``reimb_gov_vehicle_fare``)."""
    set_audit_context(session, actor_id=actor_user_id)
    claim = await _owned_editable_claim(
        session, claim_id=claim_id, actor_user_id=actor_user_id
    )

    live = (
        (
            await session.execute(
                select(ReimbItineraryLeg)
                .where(ReimbItineraryLeg.claim_id == claim.id)
                .order_by(ReimbItineraryLeg.seq, ReimbItineraryLeg.id)
            )
        )
        .scalars()
        .all()
    )
    by_id = {leg.id: leg for leg in live}

    kept: set[int] = set()
    for pos, incoming in enumerate(legs, start=1):
        data = dict(incoming)
        leg_id = data.pop("id", None)
        unknown = set(data) - _LEG_FIELDS
        if unknown:
            raise ValueError(f"unknown leg fields: {sorted(unknown)}")

        if leg_id is not None:
            row = by_id.get(leg_id)
            if row is None:
                raise errors.leg_unknown(leg_id)
            kept.add(leg_id)
        else:
            row = ReimbItineraryLeg(claim_id=claim.id)
            session.add(row)

        for field, value in data.items():
            if field == "fare" and value is not None:
                value = to_money(value)
            setattr(row, field, value)
        row.seq = pos
        row.per_diem_pct = None
        row.per_diem_amount = None
        row.leg_total = None

    for leg in live:
        if leg.id not in kept:
            soft_delete(leg, actor_id=actor_user_id)

    if claim.totals:
        claim.totals = {}
    await session.flush()
    return claim


async def recompute_totals(
    session: AsyncSession, *, claim_id: int, actor_user_id: int
) -> ReimbClaim:
    """The money step's refresh: the same owner+editable guard as every draft
    write, then delegate to ``compute_claim_totals`` (which reads the persisted
    ``other_total`` column). Flushes; the caller owns the commit."""
    claim = await _owned_editable_claim(
        session, claim_id=claim_id, actor_user_id=actor_user_id
    )
    await compute_claim_totals(
        session, claim_id=claim.id, actor_user_id=actor_user_id
    )
    return claim
