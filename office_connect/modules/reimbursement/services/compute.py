"""Load → compute → persist wrapper around the pure per-diem core.

``compute_claim_totals`` is the module's single money-computation entry point
(wizard save, resubmit-after-return, and the R-4-app workflow hooks all call it).
It writes the per-leg computed columns + the claim's ``totals`` JSONB snapshot in
the caller's session and flushes; **the caller owns the commit** (same contract as
``allocate_reference_number``). Recompute is idempotent — every computed field is
overwritten wholesale, and the audit chain records the ``totals`` diff.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.money import money_str, to_money
from office_connect.core.session import set_audit_context
from office_connect.core.time import utc_now
from office_connect.modules.reimbursement.models import (
    ReimbCashAdvance,
    ReimbClaim,
    ReimbConfig,
    ReimbDteCluster,
    ReimbItineraryLeg,
    ReimbRegionCluster,
)
from office_connect.modules.reimbursement.services import errors
from office_connect.modules.reimbursement.services.per_diem import (
    APPORTIONMENT_KEY,
    DEPARTURE_RATE_KEY,
    GOV_VEHICLE,
    ConfigRow,
    LegInput,
    PerDiemResult,
    RateRow,
    RegionRow,
    compute_per_diem,
    settle,
)

_ZERO = Decimal("0.00")
_CONFIG_KEYS = (APPORTIONMENT_KEY, DEPARTURE_RATE_KEY)

TOTALS_VERSION = 1


async def compute_claim_totals(
    session: AsyncSession,
    *,
    claim_id: int,
    other_total: Decimal | None = None,
    actor_user_id: int | None = None,
) -> PerDiemResult:
    """Compute and persist a claim's per-diem breakdown + totals.

    Writes ``per_diem_pct``/``per_diem_amount``/``leg_total`` on every live leg and
    the ``totals`` JSONB on the claim, then flushes; the caller owns the commit.
    ``other_total=None`` (the default) uses the claim's persisted ``other_total``
    column; an explicit value is persisted to the column first — one source of
    truth either way, so resubmit's recompute can never lose "other" (R-2-wizard).
    Raises ``services.errors`` factories on any data problem (fail-closed)."""
    if other_total is not None and other_total < 0:
        raise ValueError("other_total cannot be negative")
    set_audit_context(session, actor_id=actor_user_id)

    claim = (
        await session.execute(select(ReimbClaim).where(ReimbClaim.id == claim_id))
    ).scalar_one_or_none()
    if claim is None:
        raise errors.claim_not_found()

    legs = (
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
    regions = (
        (
            await session.execute(
                select(ReimbRegionCluster).where(
                    ReimbRegionCluster.is_active.is_(True)
                )
            )
        )
        .scalars()
        .all()
    )
    rates = (
        (
            await session.execute(
                select(ReimbDteCluster).where(ReimbDteCluster.is_active.is_(True))
            )
        )
        .scalars()
        .all()
    )
    configs = (
        (
            await session.execute(
                select(ReimbConfig).where(
                    ReimbConfig.key.in_(_CONFIG_KEYS),
                    ReimbConfig.is_active.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )

    result = compute_per_diem(
        legs=[
            LegInput(
                id=leg.id,
                seq=leg.seq,
                leg_date=leg.leg_date,
                destination_region_code=leg.destination_region_code,
                transport_mode=leg.transport_mode,
                fare=leg.fare,
                lodging_provided=leg.lodging_provided,
                meals_provided=leg.meals_provided,
            )
            for leg in legs
        ],
        date_depart=claim.date_depart,
        date_return=claim.date_return,
        claim_region_code=claim.destination_region_code,
        is_within_50km=claim.is_within_50km,
        overnight_stay=claim.overnight_stay,
        regions=[
            RegionRow(r.region_code, r.cluster, r.effective_from) for r in regions
        ],
        rates=[RateRow(r.cluster, r.daily_rate, r.effective_from) for r in rates],
        configs=[ConfigRow(c.key, c.value, c.effective_from) for c in configs],
    )

    for leg in legs:
        pct, amount = result.leg_values.get(leg.id, (0, _ZERO))
        counted_fare = (
            leg.fare
            if leg.transport_mode != GOV_VEHICLE and leg.fare is not None
            else _ZERO
        )
        leg.per_diem_pct = pct
        leg.per_diem_amount = amount
        leg.leg_total = to_money(counted_fare + amount)

    advance = _ZERO
    if claim.cash_advance_id is not None:
        ca = (
            await session.execute(
                select(ReimbCashAdvance).where(
                    ReimbCashAdvance.id == claim.cash_advance_id
                )
            )
        ).scalar_one_or_none()
        if ca is not None:
            advance = ca.amount

    if other_total is not None:
        claim.other_total = to_money(other_total)
    other = to_money(claim.other_total)
    grand = to_money(result.per_diem_total + result.transport_total + other)
    to_reimburse, to_refund = settle(grand=grand, advance=advance)

    claim.totals = _totals_json(
        result=result,
        other=other,
        grand=grand,
        advance=advance,
        to_reimburse=to_reimburse,
        to_refund=to_refund,
    )
    await session.flush()
    return result


def _totals_json(
    *,
    result: PerDiemResult,
    other: Decimal,
    grand: Decimal,
    advance: Decimal,
    to_reimburse: Decimal,
    to_refund: Decimal,
) -> dict[str, Any]:
    """The documented ``totals`` snapshot — money as 2-dp strings, percents as ints."""
    return {
        "version": TOTALS_VERSION,
        "per_diem": money_str(result.per_diem_total),
        "transport": money_str(result.transport_total),
        "other": money_str(other),
        "grand": money_str(grand),
        "advance": money_str(advance),
        "to_reimburse": money_str(to_reimburse),
        "to_refund": money_str(to_refund),
        "computed_at": utc_now().isoformat(),
        "days": [
            {
                "date": d.day.isoformat(),
                "day_type": d.day_type,
                "leg_id": d.leg_id,
                "region_code": d.region_code,
                "cluster": d.cluster,
                "daily_rate": money_str(d.daily_rate),
                "pct": d.pct,
                "components": {k: money_str(v) for k, v in d.components.items()},
                "deductions": {k: money_str(v) for k, v in d.deductions.items()},
                "amount": money_str(d.amount),
                "gated_50km": d.gated_50km,
            }
            for d in result.days
        ],
    }
