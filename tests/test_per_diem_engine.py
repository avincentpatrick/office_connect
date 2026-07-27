"""R-2 per-diem engine — pure-core unit tests (no DB).

The QA anchor is the build-spec §8 worked example: 3-day Manila trip →
₱2,200 + ₱2,200 + ₱1,100 = **₱5,500**.
"""

from datetime import date
from decimal import Decimal

import pytest

from office_connect.core.api.errors import APIError
from office_connect.modules.reimbursement.services.per_diem import (
    APPORTIONMENT_KEY,
    DEPARTURE_RATE_KEY,
    ConfigRow,
    LegInput,
    RateRow,
    RegionRow,
    compute_per_diem,
    settle,
)

_EO77 = date(2019, 3, 15)
_CFG = date(2020, 1, 1)

REGIONS = (
    RegionRow("13", "III", _EO77),  # NCR
    RegionRow("07", "II", _EO77),   # Region VII (Cebu)
    RegionRow("01", "I", _EO77),    # Region I
)
RATES = (
    RateRow("I", Decimal("1500.00"), _EO77),
    RateRow("II", Decimal("1800.00"), _EO77),
    RateRow("III", Decimal("2200.00"), _EO77),
)
CONFIGS = (
    ConfigRow(APPORTIONMENT_KEY, {"lodging": 50, "meals": 30, "incidentals": 20}, _CFG),
    ConfigRow(DEPARTURE_RATE_KEY, {"pct": 50}, _CFG),
)

JUL1, JUL2, JUL3 = date(2026, 7, 1), date(2026, 7, 2), date(2026, 7, 3)


def leg(
    id=1, seq=1, leg_date=JUL1, region=None, mode="bus", fare=None,
    lodging_provided=False, meals_provided=False,
):
    return LegInput(
        id=id, seq=seq, leg_date=leg_date, destination_region_code=region,
        transport_mode=mode, fare=Decimal(fare) if fare is not None else None,
        lodging_provided=lodging_provided, meals_provided=meals_provided,
    )


def compute(legs, **kw):
    defaults = dict(
        date_depart=None, date_return=None, claim_region_code=None,
        is_within_50km=False, overnight_stay=False,
        regions=REGIONS, rates=RATES, configs=CONFIGS,
    )
    defaults.update(kw)
    return compute_per_diem(legs=legs, **defaults)


# --- the QA anchor -----------------------------------------------------------


def test_worked_example_computes_5500():
    """Spec §8: two travel legs only — the Jul 2 working day has no leg row."""
    result = compute(
        [
            leg(id=1, seq=1, leg_date=JUL1, region="13", fare="500.00"),
            leg(id=2, seq=2, leg_date=JUL3, fare="500.00"),  # region ← claim's
        ],
        date_depart=JUL1,
        date_return=JUL3,
        claim_region_code="13",
    )
    assert [d.day_type for d in result.days] == ["arrival", "full", "return"]
    assert [d.amount for d in result.days] == [
        Decimal("2200.00"), Decimal("2200.00"), Decimal("1100.00"),
    ]
    assert result.days[1].leg_id is None  # legless full day, region carried forward
    assert result.per_diem_total == Decimal("5500.00")
    assert result.transport_total == Decimal("1000.00")
    assert result.leg_values[1] == (100, Decimal("2200.00"))
    assert result.leg_values[2] == (50, Decimal("1100.00"))


def test_cluster_switch_rates_each_day_by_its_destination():
    """Cebu (II ₱1,800) day 1 → NCR (III ₱2,200) day 2 → return day 3."""
    result = compute(
        [
            leg(id=1, seq=1, leg_date=JUL1, region="07"),
            leg(id=2, seq=2, leg_date=JUL2, region="13"),
            leg(id=3, seq=3, leg_date=JUL3, region="13"),
        ],
    )
    assert [d.cluster for d in result.days] == ["II", "III", "III"]
    assert [d.amount for d in result.days] == [
        Decimal("1800.00"), Decimal("2200.00"), Decimal("1100.00"),
    ]
    assert result.per_diem_total == Decimal("5100.00")


# --- day types ---------------------------------------------------------------


def test_return_day_is_meals_plus_incidentals_no_lodging():
    result = compute(
        [leg(id=1, leg_date=JUL1, region="13"), leg(id=2, seq=2, leg_date=JUL2)],
        claim_region_code="13",
    )
    ret = result.days[-1]
    assert ret.day_type == "return"
    assert ret.pct == 50
    assert set(ret.components) == {"meals", "incidentals"}
    assert ret.components["meals"] == Decimal("660.00")
    assert ret.components["incidentals"] == Decimal("440.00")
    assert ret.amount == Decimal("1100.00")


def test_same_day_round_trip_gets_departure_pct():
    result = compute([leg(id=1, leg_date=JUL1, region="13")])
    (day,) = result.days
    assert day.day_type == "same_day"
    assert day.pct == 50
    assert day.amount == Decimal("1100.00")  # no night → no lodging component


# --- host-provided strips ----------------------------------------------------


def test_meals_provided_strips_meals_component_on_arrival_day():
    result = compute(
        [leg(id=1, leg_date=JUL1, region="13", meals_provided=True),
         leg(id=2, seq=2, leg_date=JUL2)],
        claim_region_code="13",
    )
    arrival = result.days[0]
    assert arrival.pct == 100  # strips reduce the amount, never the day-type pct
    assert arrival.amount == Decimal("1540.00")  # 1100 lodging + 440 incidentals
    assert arrival.deductions == {"meals": Decimal("660.00")}


def test_lodging_strip_on_return_day_strips_nothing():
    """The return day has no lodging component — never double-penalize."""
    result = compute(
        [leg(id=1, leg_date=JUL1, region="13"),
         leg(id=2, seq=2, leg_date=JUL2, lodging_provided=True)],
        claim_region_code="13",
    )
    ret = result.days[-1]
    assert ret.amount == Decimal("1100.00")
    assert ret.deductions == {}


def test_both_provided_full_day_leaves_incidentals_only():
    result = compute(
        [leg(id=1, leg_date=JUL1, region="13"),
         leg(id=2, seq=2, leg_date=JUL2, lodging_provided=True, meals_provided=True),
         leg(id=3, seq=3, leg_date=JUL3)],
        claim_region_code="13",
    )
    full = result.days[1]
    assert full.day_type == "full"
    assert full.pct == 100
    assert full.amount == Decimal("440.00")
    assert set(full.deductions) == {"lodging", "meals"}


# --- 50-km gate --------------------------------------------------------------


def test_within_50km_without_overnight_pays_fare_only():
    result = compute(
        [leg(id=1, leg_date=JUL1, region="13", fare="150.00"),
         leg(id=2, seq=2, leg_date=JUL2, fare="150.00")],
        claim_region_code="13",
        is_within_50km=True,
        overnight_stay=False,
    )
    assert all(d.pct == 0 and d.amount == Decimal("0.00") for d in result.days)
    assert all(d.gated_50km for d in result.days)
    assert [d.day_type for d in result.days] == ["arrival", "return"]  # kept for audit
    assert result.per_diem_total == Decimal("0.00")
    assert result.transport_total == Decimal("300.00")


def test_within_50km_with_overnight_pays_in_full():
    result = compute(
        [leg(id=1, leg_date=JUL1, region="13"), leg(id=2, seq=2, leg_date=JUL2)],
        claim_region_code="13",
        is_within_50km=True,
        overnight_stay=True,
    )
    assert result.per_diem_total == Decimal("3300.00")
    assert not any(d.gated_50km for d in result.days)


# --- multi-leg days ----------------------------------------------------------


def test_multi_leg_day_never_double_counts():
    """Two legs on Jul 1 — the last (by seq) controls; the other gets 0%."""
    result = compute(
        [
            leg(id=1, seq=1, leg_date=JUL1, region="07", fare="800.00"),
            leg(id=2, seq=2, leg_date=JUL1, region="13", fare="200.00"),
            leg(id=3, seq=3, leg_date=JUL2),
        ],
        claim_region_code="13",
    )
    day1 = result.days[0]
    assert day1.leg_id == 2  # where the traveler ends the day
    assert day1.cluster == "III"
    assert result.leg_values[1] == (0, Decimal("0.00"))
    assert result.leg_values[2] == (100, Decimal("2200.00"))
    assert result.per_diem_total == Decimal("3300.00")  # one day counted once
    assert result.transport_total == Decimal("1000.00")  # both fares still count


# --- rounding + effective dates ---------------------------------------------


def test_components_quantize_half_up_and_sum_to_the_day_amount():
    """Synthetic ₱1,000.01 rate: quantize per component, then sum."""
    rates = (RateRow("III", Decimal("1000.01"), _EO77),)
    result = compute(
        [leg(id=1, leg_date=JUL1, region="13"), leg(id=2, seq=2, leg_date=JUL2)],
        claim_region_code="13",
        rates=rates,
    )
    arrival, ret = result.days
    assert arrival.components == {
        "lodging": Decimal("500.01"),      # 500.005 → half-up
        "meals": Decimal("300.00"),        # 300.003
        "incidentals": Decimal("200.00"),  # 200.002
    }
    assert arrival.amount == sum(arrival.components.values())
    # Return day sums its quantized components (500.00) — NOT to_money(50% × rate).
    assert ret.amount == Decimal("500.00")
    assert result.per_diem_total == arrival.amount + ret.amount


def test_mid_trip_rate_change_pays_each_day_at_its_own_rate():
    rates = RATES + (RateRow("III", Decimal("2400.00"), JUL2),)
    result = compute(
        [leg(id=1, leg_date=JUL1, region="13"), leg(id=2, seq=2, leg_date=JUL3)],
        date_depart=JUL1,
        date_return=JUL3,
        claim_region_code="13",
    )
    assert [d.amount for d in result.days] == [
        Decimal("2200.00"), Decimal("2200.00"), Decimal("1100.00"),
    ]
    result2 = compute(
        [leg(id=1, leg_date=JUL1, region="13"), leg(id=2, seq=2, leg_date=JUL3)],
        date_depart=JUL1,
        date_return=JUL3,
        claim_region_code="13",
        rates=rates,
    )
    assert [d.amount for d in result2.days] == [
        Decimal("2200.00"), Decimal("2400.00"), Decimal("1200.00"),
    ]


# --- fail-closed errors ------------------------------------------------------


def _raises(code, fn):
    with pytest.raises(APIError) as ei:
        fn()
    assert ei.value.code == code
    assert ei.value.status_code == 422
    return ei.value


def test_gov_vehicle_leg_with_fare_raises():
    _raises(
        "reimb_gov_vehicle_fare",
        lambda: compute([leg(id=1, region="13", mode="gov_vehicle", fare="350.00")]),
    )


def test_gov_vehicle_leg_without_fare_computes_and_suppresses_transport():
    result = compute([leg(id=1, region="13", mode="gov_vehicle")])
    assert result.transport_total == Decimal("0.00")
    assert result.per_diem_total == Decimal("1100.00")


def test_no_legs_raises():
    _raises("reimb_no_computable_days", lambda: compute([]))


def test_leg_without_date_raises():
    _raises(
        "reimb_leg_date_required",
        lambda: compute([leg(id=1, leg_date=None, region="13")]),
    )


def test_leg_outside_trip_dates_raises():
    _raises(
        "reimb_leg_outside_trip_dates",
        lambda: compute(
            [leg(id=1, leg_date=date(2026, 7, 5), region="13")],
            date_depart=JUL1,
            date_return=JUL3,
        ),
    )


def test_missing_region_mapping_raises():
    _raises("reimb_missing_region_cluster", lambda: compute([leg(id=1, region="99")]))


def test_no_region_anywhere_raises():
    _raises("reimb_missing_region_cluster", lambda: compute([leg(id=1)]))


def test_missing_rate_raises():
    _raises(
        "reimb_missing_dte_rate",
        lambda: compute([leg(id=1, region="13")], rates=(RATES[0], RATES[1])),
    )


def test_invalid_apportionment_raises():
    bad = (
        ConfigRow(APPORTIONMENT_KEY, {"lodging": 50, "meals": 30, "incidentals": 30}, _CFG),
        CONFIGS[1],
    )
    _raises(
        "reimb_config_invalid", lambda: compute([leg(id=1, region="13")], configs=bad)
    )


def test_departure_pct_must_equal_meals_plus_incidentals():
    bad = (CONFIGS[0], ConfigRow(DEPARTURE_RATE_KEY, {"pct": 60}, _CFG))
    _raises(
        "reimb_config_invalid", lambda: compute([leg(id=1, region="13")], configs=bad)
    )


def test_missing_config_raises():
    _raises(
        "reimb_config_missing",
        lambda: compute([leg(id=1, region="13")], configs=(CONFIGS[0],)),
    )


# --- settlement --------------------------------------------------------------


def test_settle_sign_matrix():
    g, a = Decimal("6734.00"), Decimal("5000.00")
    assert settle(grand=g, advance=a) == (Decimal("1734.00"), Decimal("0.00"))
    assert settle(grand=g, advance=Decimal("8000.00")) == (
        Decimal("0.00"), Decimal("1266.00"),
    )
    assert settle(grand=g, advance=g) == (Decimal("0.00"), Decimal("0.00"))
    assert settle(grand=g, advance=Decimal("0.00")) == (g, Decimal("0.00"))
