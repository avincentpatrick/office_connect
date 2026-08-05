"""R-9 — the pilot demo cast (spec §14's fixture list, R-1's deferral discharged).

Spec §14 names a fixture set *"built in R-1, used everywhere"*: six synthetic
travellers including one JO/COS, ten trips including the §8 worked example, and
an open cash advance aged 25 days. R-1 shipped the config/catalog seeds and
deferred the rest; this is where it lands, because R-9 is the first thing that
needs it — a pilot demo with an empty database demonstrates nothing.

**What is worth testing about fixture data**, since most of it is just rows:

1. **Idempotence.** A demo box gets reloaded, and a loader that duplicated its
   cast on every run would fill the board with copies of the same trip.
2. **The money is the SERVER's.** ₱6,500 is asserted here and written nowhere in
   ``fixtures.py`` — if the per-diem engine ever drifts, this fails, which makes
   the fixture a second anchor for spec §8's worked example rather than a
   restatement of it.
3. **The demo actually demonstrates.** An advance aged into the due-soon window,
   a taxi fare over the RER threshold, a JO/COS traveller — each exists to make
   one rule visible on screen, and each is easy to break by editing a date.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select

from office_connect.core.models import Staff
from office_connect.core.time import to_manila, utc_now
from office_connect.modules.reimbursement import fixtures
from office_connect.modules.reimbursement.models import ReimbCashAdvance, ReimbClaim
from office_connect.modules.reimbursement.services import deadline as dl


@pytest.fixture
async def loaded(app_session):
    """Load the cast once for the module. Deliberately NOT undone: this is
    dev-fixture data keyed on a ``[demo]`` marker and an ``D-`` employee block,
    it is idempotent, and it is exactly what a developer wants left behind. It
    touches no seeded reference row, so ``seed_guard`` stays green."""
    result = await fixtures.load_pilot_fixtures(app_session)
    await app_session.commit()
    return result


async def test_the_loader_is_idempotent(app_session, loaded):
    """A second run creates nothing. The demo box gets reloaded — often by
    someone who is not sure whether they already ran it."""
    again = await fixtures.load_pilot_fixtures(app_session)
    await app_session.commit()

    assert again["travellers_created"] == 0
    assert again["trips_created"] == 0
    assert again["cash_advance_created"] is False
    assert again["trips_total"] == len(fixtures._TRIPS) == 10
    assert again["travellers_total"] == len(fixtures._TRAVELLERS) == 6


async def test_the_worked_example_still_computes_5500_per_diem(app_session, loaded):
    """**The §8 anchor, computed by the server.**

    ₱6,500 appears nowhere in ``fixtures.py`` — the file supplies a 3-day NCR
    trip with two ₱500 fares and asks ``compute_claim_totals`` what that costs.
    So this assertion is a second, independent anchor on the per-diem engine
    (₱2,200/day NCR × 50/30/20 apportionment × the 50%-departure-day rule =
    ₱5,500, plus ₱1,000 transport), reached through a different path than
    ``test_per_diem_engine.py`` takes.
    """
    assert loaded["computed_grand_totals"]["worked-example"] == "6500.00"

    claim = (
        await app_session.execute(
            select(ReimbClaim).where(
                ReimbClaim.purpose.like("%worked example%"),
                ReimbClaim.purpose.startswith(fixtures.DEMO_TAG),
            )
        )
    ).scalar_one()
    assert claim.totals["per_diem"] == "5500.00"
    assert claim.totals["transport"] == "1000.00"
    assert claim.totals["grand"] == "6500.00"


async def test_the_cash_advance_is_open_and_inside_the_due_soon_window(
    app_session, loaded
):
    """Spec §14 asks for an advance "aged 25 days (near-overdue)", and the point
    of *near* is that a demo must show the countdown ring in its amber state and
    the COA consequence copy. An advance comfortably inside its 30 days renders
    a calm grey number nobody notices.

    The deadline is resolved by ``services/cash_advance``, not by this fixture —
    a bare INSERT left ``deadline_date`` NULL on the first attempt, which is an
    advance with no countdown at all.
    """
    advance = (
        await app_session.execute(
            select(ReimbCashAdvance).where(ReimbCashAdvance.dv_no == "DV-DEMO-0001")
        )
    ).scalar_one()

    assert advance.status == "open"
    assert advance.amount == Decimal("18000.00")
    assert advance.deadline_date is not None, "no deadline means no countdown"

    today = to_manila(utc_now()).date()
    remaining = dl.days_remaining(deadline=advance.deadline_date, today=today)
    assert 0 < remaining <= 7, f"expected the due-soon window, got D-{remaining}"
    assert dl.deadline_state(deadline=advance.deadline_date, today=today) == dl.DUE_SOON


async def test_exactly_one_traveller_is_jo_cos(app_session, loaded):
    """``is_jo_cos`` is what makes the conditional checklist item appear (R-3),
    so a cast with none of them cannot demonstrate the checklist engine — and a
    cast where they are ALL JO/COS cannot demonstrate that it is conditional."""
    rows = (
        (
            await app_session.execute(
                select(Staff).where(
                    Staff.employee_no.startswith(fixtures._EMPLOYEE_PREFIX)
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 6
    jo_cos = [s for s in rows if s.employment_status == "job_order"]
    assert len(jo_cos) == 1, [s.employment_status for s in rows]

    claim = (
        await app_session.execute(
            select(ReimbClaim).where(ReimbClaim.claimant_id == jo_cos[0].id)
        )
    ).scalar_one()
    assert claim.is_jo_cos is True, "derived from employment status, not asserted"


async def test_a_taxi_fare_crosses_the_rer_threshold(app_session, loaded):
    """Spec §14 asks for a ">₱300 taxi fare" because that is what fires the
    `amount_threshold` auto-check and demands a Reimbursement Expense Receipt.
    Under the threshold it is an ordinary fare and the demo shows nothing."""
    from office_connect.modules.reimbursement.models import ReimbItineraryLeg

    claim = (
        await app_session.execute(
            select(ReimbClaim).where(
                ReimbClaim.purpose.like("%RER threshold%"),
                ReimbClaim.purpose.startswith(fixtures.DEMO_TAG),
            )
        )
    ).scalar_one()
    fares = (
        (
            await app_session.execute(
                select(ReimbItineraryLeg.fare).where(
                    ReimbItineraryLeg.claim_id == claim.id,
                    ReimbItineraryLeg.transport_mode == "taxi",
                )
            )
        )
        .scalars()
        .all()
    )
    assert fares and all(f > Decimal("300.00") for f in fares), fares


async def test_nothing_in_the_cast_is_submitted(app_session, loaded):
    """The deliberate boundary: this loader writes DATA, never workflow history.

    Fabricating approvals would mean writing hash-chained audit rows asserting
    that people made decisions they never made — in the one structure whose
    whole value is that you can believe what it says. The manual test guide
    (module doc §6) drives the chain by hand instead.
    """
    claims = (
        (
            await app_session.execute(
                select(ReimbClaim).where(
                    ReimbClaim.purpose.startswith(fixtures.DEMO_TAG)
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(claims) == 10
    assert all(c.workflow_instance_id is None for c in claims)
    assert all(c.status == "draft" for c in claims)
    assert all(c.ref_no is None for c in claims), "no RB- number is burned"


async def test_every_trip_computed_a_grand_total(loaded):
    """A demo trip with no totals renders blank money everywhere it appears. The
    within-50km commuter is the one legitimately-small figure (fares only, 0%
    DTE), and it must still be a real computed number rather than absent."""
    totals = loaded["computed_grand_totals"]
    assert len(totals) == 10
    assert all(value is not None for value in totals.values()), totals
    assert totals["within-50km-commute"] == "240.00"  # fares only, no DTE
    assert totals["gov-vehicle"] == "2250.00"  # DTE only, fares suppressed
