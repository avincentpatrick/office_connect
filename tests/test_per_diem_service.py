"""R-2 compute service — persists leg fields + the ``totals`` snapshot (app_session)."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from office_connect.core.api.errors import APIError
from office_connect.modules.reimbursement.models import ReimbClaim, ReimbItineraryLeg
from office_connect.modules.reimbursement.seeds import apply_reimbursement_seeds
from office_connect.modules.reimbursement.services import (
    TOTALS_VERSION,
    compute_claim_totals,
)
from tests import reimbursement_trip_factories as trips
from tests.reimbursement_helpers import make_claim, make_staff

_TOTALS_KEYS = {
    "version", "per_diem", "transport", "other", "grand", "advance",
    "to_reimburse", "to_refund", "computed_at", "days",
}


async def _seeded(app_session):
    await apply_reimbursement_seeds(app_session)
    await app_session.commit()


async def test_persists_leg_fields_and_the_totals_shape(app_session):
    await _seeded(app_session)
    claim, _ = await trips.manila_3day(app_session)
    await compute_claim_totals(app_session, claim_id=claim.id)
    await app_session.commit()

    claim = (
        await app_session.execute(select(ReimbClaim).where(ReimbClaim.id == claim.id))
    ).scalar_one()
    totals = claim.totals
    assert set(totals) == _TOTALS_KEYS
    assert totals["version"] == TOTALS_VERSION
    assert totals["per_diem"] == "5500.00"  # the spec §8 QA anchor
    assert totals["transport"] == "1000.00"
    assert totals["other"] == "0.00"
    assert totals["grand"] == "6500.00"
    assert totals["advance"] == "0.00"
    assert totals["to_reimburse"] == "6500.00"  # no CA → straight reimbursement
    assert totals["to_refund"] == "0.00"
    assert len(totals["days"]) == 3
    day1, day2, day3 = totals["days"]
    assert (day1["day_type"], day1["pct"], day1["amount"]) == ("arrival", 100, "2200.00")
    assert (day2["day_type"], day2["leg_id"]) == ("full", None)
    assert (day3["day_type"], day3["pct"], day3["amount"]) == ("return", 50, "1100.00")
    assert day1["components"] == {
        "lodging": "1100.00", "meals": "660.00", "incidentals": "440.00",
    }

    legs = (
        (
            await app_session.execute(
                select(ReimbItineraryLeg)
                .where(ReimbItineraryLeg.claim_id == claim.id)
                .order_by(ReimbItineraryLeg.seq)
            )
        )
        .scalars()
        .all()
    )
    assert (legs[0].per_diem_pct, legs[0].per_diem_amount) == (100, Decimal("2200.00"))
    assert legs[0].leg_total == Decimal("2700.00")  # fare 500 + per-diem 2200
    assert (legs[1].per_diem_pct, legs[1].per_diem_amount) == (50, Decimal("1100.00"))
    assert legs[1].leg_total == Decimal("1600.00")


async def test_recompute_is_idempotent(app_session):
    await _seeded(app_session)
    claim, _ = await trips.cluster_switch_trip(app_session)
    await compute_claim_totals(app_session, claim_id=claim.id)
    await app_session.commit()
    first = dict(claim.totals)

    await compute_claim_totals(app_session, claim_id=claim.id)
    await app_session.commit()
    second = dict(claim.totals)

    first.pop("computed_at")
    second.pop("computed_at")
    assert first == second
    assert second["per_diem"] == "5100.00"  # 1800 + 2200 + 1100


async def test_other_total_lands_in_grand(app_session):
    await _seeded(app_session)
    claim, _ = await trips.manila_3day(app_session)
    await compute_claim_totals(
        app_session, claim_id=claim.id, other_total=Decimal("250.00")
    )
    await app_session.commit()
    assert claim.totals["other"] == "250.00"
    assert claim.totals["grand"] == "6750.00"


async def test_ca_settlement_refund_and_reimburse(app_session):
    await _seeded(app_session)

    refund_claim, _ = await trips.ca_refund_trip(app_session)
    await compute_claim_totals(app_session, claim_id=refund_claim.id)
    await app_session.commit()
    assert refund_claim.totals["advance"] == "8000.00"
    assert refund_claim.totals["to_refund"] == "1500.00"
    assert refund_claim.totals["to_reimburse"] == "0.00"

    reimb_claim, _ = await trips.ca_reimburse_trip(app_session)
    await compute_claim_totals(app_session, claim_id=reimb_claim.id)
    await app_session.commit()
    assert reimb_claim.totals["advance"] == "5000.00"
    assert reimb_claim.totals["to_reimburse"] == "1500.00"
    assert reimb_claim.totals["to_refund"] == "0.00"


async def test_50km_gate_and_gov_vehicle_trips(app_session):
    await _seeded(app_session)

    commuter, _ = await trips.within_50km_commuter(app_session)
    await compute_claim_totals(app_session, claim_id=commuter.id)
    assert commuter.totals["per_diem"] == "0.00"
    assert commuter.totals["transport"] == "1000.00"
    assert all(d["gated_50km"] for d in commuter.totals["days"])

    overnight, _ = await trips.within_50km_overnight(app_session)
    await compute_claim_totals(app_session, claim_id=overnight.id)
    assert overnight.totals["per_diem"] == "5500.00"

    gov, _ = await trips.gov_vehicle_trip(app_session)
    await compute_claim_totals(app_session, claim_id=gov.id)
    await app_session.commit()
    assert gov.totals["transport"] == "0.00"
    assert gov.totals["per_diem"] == "5500.00"


async def test_host_provided_trip_strips_components(app_session):
    await _seeded(app_session)
    claim, _ = await trips.host_provided_trip(app_session)
    await compute_claim_totals(app_session, claim_id=claim.id)
    await app_session.commit()
    # Arrival day stripped to incidentals only (440); full + return days untouched.
    assert claim.totals["per_diem"] == "3740.00"  # 440 + 2200 + 1100
    assert claim.totals["days"][0]["deductions"] == {
        "lodging": "1100.00", "meals": "660.00",
    }


async def test_claim_not_found_raises_404(app_session):
    await _seeded(app_session)
    with pytest.raises(APIError) as ei:
        await compute_claim_totals(app_session, claim_id=999_999_999)
    assert ei.value.status_code == 404
    assert ei.value.code == "reimb_claim_not_found"


async def test_attestation_columns_default_false(app_session):
    staff = await make_staff(app_session)
    claim = await make_claim(app_session, claimant_id=staff.id)
    await app_session.commit()
    fresh = (
        await app_session.execute(select(ReimbClaim).where(ReimbClaim.id == claim.id))
    ).scalar_one()
    assert fresh.is_within_50km is False
    assert fresh.overnight_stay is False
