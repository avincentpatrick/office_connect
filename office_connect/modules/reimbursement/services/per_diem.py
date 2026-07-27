"""The per-diem computation core — pure, no I/O (mirrors ``core/workflow/guards.py``).

Computes a claim's EO 77 travel entitlement as a **per-day breakdown** over the trip
span, then attributes each day to its *controlling leg* (the last leg of that date —
where the traveler ends the day is where they lodge, so its region drives that day's
cluster). Other legs on the same date get 0% — double-claiming a day is structurally
impossible. Days with no leg row (a full working day at the destination) still
produce a day entry, carrying the previous day's region forward.

Rules (research digest ``ph-travel-reimbursement-rules.md`` + module delta register):
- Day types: ``arrival``/``full`` = 100%; ``return`` = the configured departure-day
  pct (50% — meals + incidentals, NO lodging component); a one-day round trip is
  ``same_day`` = the same 50% (no night → no lodging component; flagged for
  accountant confirmation).
- Host-provided strips remove a *component if present*: lodging 50% / meals 30%.
  A lodging strip on a return day strips nothing — the component is already absent.
- 50-km gate (claim attestations): within 50 km without an overnight stay → fare
  only, 0% DTE on every day (supersedes the spec §8 lodging-only strip).
- Government-vehicle legs must not carry a fare (fail-closed 422, never a silent drop).
- Rates, region→cluster map, and configs are all effective-dated and resolved
  **as of each day** (a mid-trip rate change pays each day at its own rate).
- Each component is quantized (``to_money``, ROUND_HALF_UP) *after* its percentage is
  applied, then the quantized components are summed — a printed day row always sums
  exactly to the day amount, and the days to the per-diem total (audit re-performance).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Sequence

from office_connect.core.money import to_money
from office_connect.modules.reimbursement.services import errors

GOV_VEHICLE = "gov_vehicle"

APPORTIONMENT_KEY = "per_diem.apportionment"
DEPARTURE_RATE_KEY = "per_diem.departure_day_rate"

_ZERO = Decimal("0.00")


@dataclass(frozen=True, slots=True)
class LegInput:
    id: int | None
    seq: int
    leg_date: date | None
    destination_region_code: str | None
    transport_mode: str | None
    fare: Decimal | None
    lodging_provided: bool = False
    meals_provided: bool = False


@dataclass(frozen=True, slots=True)
class RegionRow:
    region_code: str
    cluster: str
    effective_from: date


@dataclass(frozen=True, slots=True)
class RateRow:
    cluster: str
    daily_rate: Decimal
    effective_from: date


@dataclass(frozen=True, slots=True)
class ConfigRow:
    key: str
    value: dict
    effective_from: date


@dataclass(frozen=True, slots=True)
class DayBreakdown:
    day: date
    day_type: str  # arrival | full | return | same_day
    leg_id: int | None  # controlling leg; None = legless day
    region_code: str
    cluster: str
    daily_rate: Decimal
    pct: int  # 100/50/0 — the day-type GROSS pct; strips reduce amount, not pct
    components: dict[str, Decimal]
    deductions: dict[str, Decimal]  # host-provided strips actually applied
    amount: Decimal
    gated_50km: bool


@dataclass(frozen=True, slots=True)
class PerDiemResult:
    days: tuple[DayBreakdown, ...]
    # leg_id -> (per_diem_pct, per_diem_amount); non-controlling legs -> (0, 0.00)
    leg_values: dict[int, tuple[int, Decimal]]
    per_diem_total: Decimal
    transport_total: Decimal


def _as_of(rows, day: date, keyattr: str, keyval: str):
    """Latest row for ``keyval`` with ``effective_from <= day``, or None."""
    best = None
    for row in rows:
        if getattr(row, keyattr) != keyval or row.effective_from > day:
            continue
        if best is None or row.effective_from > best.effective_from:
            best = row
    return best


def _apportionment(configs: Sequence[ConfigRow], day: date) -> dict[str, int]:
    row = _as_of(configs, day, "key", APPORTIONMENT_KEY)
    if row is None:
        raise errors.config_missing(APPORTIONMENT_KEY, day)
    value = row.value
    try:
        parts = {k: int(value[k]) for k in ("lodging", "meals", "incidentals")}
    except (KeyError, TypeError, ValueError):
        raise errors.config_invalid(
            APPORTIONMENT_KEY, "needs integer lodging/meals/incidentals percents."
        )
    if sum(parts.values()) != 100:
        raise errors.config_invalid(APPORTIONMENT_KEY, "percents must sum to 100.")
    return parts


def _departure_pct(
    configs: Sequence[ConfigRow], day: date, apportionment: dict[str, int]
) -> int:
    row = _as_of(configs, day, "key", DEPARTURE_RATE_KEY)
    if row is None:
        raise errors.config_missing(DEPARTURE_RATE_KEY, day)
    try:
        pct = int(row.value["pct"])
    except (KeyError, TypeError, ValueError):
        raise errors.config_invalid(DEPARTURE_RATE_KEY, "needs an integer 'pct'.")
    if pct != apportionment["meals"] + apportionment["incidentals"]:
        raise errors.config_invalid(
            DEPARTURE_RATE_KEY,
            "the departure-day pct must equal meals + incidentals "
            "(the day has no lodging component).",
        )
    return pct


def compute_per_diem(
    *,
    legs: Sequence[LegInput],
    date_depart: date | None,
    date_return: date | None,
    claim_region_code: str | None,
    is_within_50km: bool,
    overnight_stay: bool,
    regions: Sequence[RegionRow],
    rates: Sequence[RateRow],
    configs: Sequence[ConfigRow],
) -> PerDiemResult:
    """Compute the per-day breakdown + per-leg attribution. Raises ``errors.*``."""
    if not legs:
        raise errors.no_computable_days()
    for leg in legs:
        if leg.leg_date is None:
            raise errors.leg_date_required(leg.seq)
        if (
            leg.transport_mode == GOV_VEHICLE
            and leg.fare is not None
            and leg.fare != 0
        ):
            raise errors.gov_vehicle_fare(leg.seq)

    if date_depart is not None and date_return is not None:
        first, last = date_depart, date_return
    else:
        leg_dates = [leg.leg_date for leg in legs]
        first, last = min(leg_dates), max(leg_dates)
    if last < first:
        raise errors.no_computable_days()
    for leg in legs:
        if not first <= leg.leg_date <= last:
            raise errors.leg_outside_trip_dates(leg.leg_date)

    by_date: dict[date, list[LegInput]] = {}
    for leg in legs:
        by_date.setdefault(leg.leg_date, []).append(leg)

    gated = is_within_50km and not overnight_stay
    days: list[DayBreakdown] = []
    leg_values: dict[int, tuple[int, Decimal]] = {
        leg.id: (0, _ZERO) for leg in legs if leg.id is not None
    }
    prev_region: str | None = None
    span_days = (last - first).days + 1

    for offset in range(span_days):
        day = first + timedelta(days=offset)
        todays = by_date.get(day, [])
        controlling = (
            max(todays, key=lambda leg: (leg.seq, leg.id or 0)) if todays else None
        )

        if controlling is not None and controlling.destination_region_code:
            region = controlling.destination_region_code
        elif controlling is None and prev_region is not None:
            region = prev_region
        else:
            region = claim_region_code
        if region is None:
            raise errors.missing_region_cluster(day, None)
        prev_region = region

        region_row = _as_of(regions, day, "region_code", region)
        if region_row is None:
            raise errors.missing_region_cluster(day, region)
        rate_row = _as_of(rates, day, "cluster", region_row.cluster)
        if rate_row is None:
            raise errors.missing_dte_rate(region_row.cluster, day)

        apportionment = _apportionment(configs, day)
        departure_pct = _departure_pct(configs, day, apportionment)

        if span_days == 1:
            day_type, pct = "same_day", departure_pct
        elif day == first:
            day_type, pct = "arrival", 100
        elif day == last:
            day_type, pct = "return", departure_pct
        else:
            day_type, pct = "full", 100

        # Component set from day type; return/same_day drop lodging — that IS the 50%.
        component_names = (
            ("lodging", "meals", "incidentals")
            if day_type in ("arrival", "full")
            else ("meals", "incidentals")
        )
        components = {
            name: to_money(rate_row.daily_rate * apportionment[name] / 100)
            for name in component_names
        }

        # Host-provided strips remove a component IF PRESENT (never double-penalize).
        deductions: dict[str, Decimal] = {}
        if controlling is not None:
            if controlling.lodging_provided and "lodging" in components:
                deductions["lodging"] = components.pop("lodging")
            if controlling.meals_provided and "meals" in components:
                deductions["meals"] = components.pop("meals")

        if gated:
            pct, components, deductions = 0, {}, {}
        amount = to_money(sum(components.values(), _ZERO))

        days.append(
            DayBreakdown(
                day=day,
                day_type=day_type,
                leg_id=controlling.id if controlling is not None else None,
                region_code=region,
                cluster=region_row.cluster,
                daily_rate=rate_row.daily_rate,
                pct=pct,
                components=components,
                deductions=deductions,
                amount=amount,
                gated_50km=gated,
            )
        )
        if controlling is not None and controlling.id is not None:
            leg_values[controlling.id] = (pct, amount)

    per_diem_total = to_money(sum((d.amount for d in days), _ZERO))
    transport_total = to_money(
        sum(
            (
                leg.fare
                for leg in legs
                if leg.transport_mode != GOV_VEHICLE and leg.fare is not None
            ),
            _ZERO,
        )
    )
    return PerDiemResult(
        days=tuple(days),
        leg_values=leg_values,
        per_diem_total=per_diem_total,
        transport_total=transport_total,
    )


def settle(*, grand: Decimal, advance: Decimal) -> tuple[Decimal, Decimal]:
    """``(to_reimburse, to_refund)`` — exactly one nonzero, or both zero.

    ``advance − grand``: positive = refund due (record the OR); negative =
    "Reimbursement Due" for the difference (build spec §6.2)."""
    diff = to_money(advance) - to_money(grand)
    return (to_money(max(-diff, _ZERO)), to_money(max(diff, _ZERO)))
