"""Representative synthetic trips for the R-2 engine tests (the R-1 deferral).

Each factory builds a staff + claim + legs against the seeded EO 77 config and
returns ``(claim, legs)``; CA trips link their advance via ``claim.cash_advance_id``.
Reused by the wizard (R-2) and workflow-definition (R-4-app) increments later.
"""

from __future__ import annotations

from datetime import date

from tests.reimbursement_helpers import (
    make_cash_advance,
    make_claim,
    make_leg,
    make_staff,
)

JUL1, JUL2, JUL3 = date(2026, 7, 1), date(2026, 7, 2), date(2026, 7, 3)


async def manila_3day(session, **claim_kw):
    """The spec §8 worked example: 3-day NCR trip, two travel legs, ₱500 fare each.

    Per-diem ₱5,500 + transport ₱1,000 → grand ₱6,500."""
    staff = await make_staff(session)
    claim = await make_claim(
        session,
        claimant_id=staff.id,
        destination_region_code="13",
        date_depart=JUL1,
        date_return=JUL3,
        **claim_kw,
    )
    legs = [
        await make_leg(
            session, claim_id=claim.id, seq=1, leg_date=JUL1,
            destination_region_code="13", transport_mode="bus", fare="500.00",
        ),
        await make_leg(
            session, claim_id=claim.id, seq=2, leg_date=JUL3,
            transport_mode="bus", fare="500.00",
        ),
    ]
    return claim, legs


async def cluster_switch_trip(session):
    """Cebu (II ₱1,800) day 1 → NCR (III ₱2,200) day 2 → return day 3."""
    staff = await make_staff(session)
    claim = await make_claim(
        session,
        claimant_id=staff.id,
        destination_region_code="13",
        date_depart=JUL1,
        date_return=JUL3,
    )
    legs = [
        await make_leg(
            session, claim_id=claim.id, seq=1, leg_date=JUL1,
            destination_region_code="07", transport_mode="plane", fare="3200.00",
        ),
        await make_leg(
            session, claim_id=claim.id, seq=2, leg_date=JUL2,
            destination_region_code="13", transport_mode="plane", fare="2800.00",
        ),
        await make_leg(
            session, claim_id=claim.id, seq=3, leg_date=JUL3,
            transport_mode="bus", fare="500.00",
        ),
    ]
    return claim, legs


async def same_day_trip(session):
    staff = await make_staff(session)
    claim = await make_claim(
        session,
        claimant_id=staff.id,
        destination_region_code="13",
        date_depart=JUL1,
        date_return=JUL1,
    )
    legs = [
        await make_leg(
            session, claim_id=claim.id, seq=1, leg_date=JUL1,
            transport_mode="bus", fare="300.00",
        )
    ]
    return claim, legs


async def within_50km_commuter(session):
    """Within 50 km, no overnight → transport fare only, 0% DTE."""
    claim, legs = await manila_3day(session, is_within_50km=True)
    return claim, legs


async def within_50km_overnight(session):
    """Within 50 km WITH the overnight attestation → full computation."""
    claim, legs = await manila_3day(session, is_within_50km=True, overnight_stay=True)
    return claim, legs


async def host_provided_trip(session):
    """3-day NCR trip; host provides meals on arrival and lodging overnight."""
    staff = await make_staff(session)
    claim = await make_claim(
        session,
        claimant_id=staff.id,
        destination_region_code="13",
        date_depart=JUL1,
        date_return=JUL3,
    )
    legs = [
        await make_leg(
            session, claim_id=claim.id, seq=1, leg_date=JUL1,
            transport_mode="bus", fare="500.00",
            lodging_provided=True, meals_provided=True,
        ),
        await make_leg(
            session, claim_id=claim.id, seq=2, leg_date=JUL3,
            transport_mode="bus", fare="500.00",
        ),
    ]
    return claim, legs


async def gov_vehicle_trip(session):
    """Government vehicle both ways — no fares anywhere."""
    staff = await make_staff(session)
    claim = await make_claim(
        session,
        claimant_id=staff.id,
        destination_region_code="13",
        date_depart=JUL1,
        date_return=JUL3,
    )
    legs = [
        await make_leg(
            session, claim_id=claim.id, seq=1, leg_date=JUL1,
            transport_mode="gov_vehicle",
        ),
        await make_leg(
            session, claim_id=claim.id, seq=2, leg_date=JUL3,
            transport_mode="gov_vehicle",
        ),
    ]
    return claim, legs


async def ca_refund_trip(session):
    """Advance ₱8,000 > grand ₱6,500 → ₱1,500 refund due (record the OR)."""
    staff = await make_staff(session)
    ca = await make_cash_advance(session, claimant_id=staff.id, amount="8000.00")
    claim = await make_claim(
        session,
        claimant_id=staff.id,
        kind="liquidation",
        destination_region_code="13",
        date_depart=JUL1,
        date_return=JUL3,
        cash_advance_id=ca.id,
    )
    legs = [
        await make_leg(
            session, claim_id=claim.id, seq=1, leg_date=JUL1,
            destination_region_code="13", transport_mode="bus", fare="500.00",
        ),
        await make_leg(
            session, claim_id=claim.id, seq=2, leg_date=JUL3,
            transport_mode="bus", fare="500.00",
        ),
    ]
    return claim, legs


async def ca_reimburse_trip(session):
    """Advance ₱5,000 < grand ₱6,500 → ₱1,500 "Reimbursement Due"."""
    staff = await make_staff(session)
    ca = await make_cash_advance(session, claimant_id=staff.id, amount="5000.00")
    claim = await make_claim(
        session,
        claimant_id=staff.id,
        kind="liquidation",
        destination_region_code="13",
        date_depart=JUL1,
        date_return=JUL3,
        cash_advance_id=ca.id,
    )
    legs = [
        await make_leg(
            session, claim_id=claim.id, seq=1, leg_date=JUL1,
            destination_region_code="13", transport_mode="bus", fare="500.00",
        ),
        await make_leg(
            session, claim_id=claim.id, seq=2, leg_date=JUL3,
            transport_mode="bus", fare="500.00",
        ),
    ]
    return claim, legs
