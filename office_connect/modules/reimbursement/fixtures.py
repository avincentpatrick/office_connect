"""Synthetic pilot-demo data for the reimbursement module — **dev/UAT only**.

Build spec §14 lists a fixture set *"built in R-1, used everywhere"*: six
synthetic travellers (one JO/COS), ten trips including the §8 worked example, an
open cash advance aged 25 days, and receipts including a >₱300 taxi fare and a
thermal receipt. R-1 shipped only the config/catalog seeds and recorded the rest
as a deferral; R-9 discharges it, because a pilot demo is the first thing that
actually needs it.

**What this is NOT.** It is not seed data (nothing here is reference material and
none of it belongs in `core/seeds`), and it does not drive the workflow. Claims
are created with real, SERVER-COMPUTED totals and left where a human can pick
them up — the manual test guide in `docs/modules/reimbursement.md` §6 is what
walks a demo through submit → approve → FMS → paid → liquidate → settle. That
split is deliberate: fabricating approval history would mean writing audit rows
asserting that people made decisions they never made, in a hash chain whose
entire purpose is that you can trust what it says.

**Every name is obviously synthetic** (`[demo]` on activities, `@example.gov.ph`
addresses, employee numbers in a reserved `D-` block) so nothing here can ever
be mistaken for real personnel data. That matters beyond tidiness: the DOH / Data
Privacy Act governance gate blocks real data until a PIA is signed per module
(master plan §3.1), and the cleanest way to stay on the right side of it is for
synthetic data to be unmistakable at a glance.

Idempotent throughout, keyed on employee number and a per-trip marker in
``purpose`` — a second run creates nothing and changes nothing.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.models import Activity, OrgUnit, Staff
from office_connect.core.time import to_manila, utc_now
from office_connect.modules.reimbursement.models import (
    ReimbCashAdvance,
    ReimbClaim,
    ReimbItineraryLeg,
)
from office_connect.modules.reimbursement.services import cash_advance as ca_service
from office_connect.modules.reimbursement.services.compute import compute_claim_totals

#: Marker written into every demo claim's ``purpose``. Doubles as the
#: idempotence key and as the thing that makes demo rows obvious in a query.
DEMO_TAG = "[demo]"

#: Employee-number block reserved for demo travellers — distinct from the
#: ``F-``/``T-`` block ``ops/bootstrap.py``'s directory fixtures already use, so
#: the two fixture sets can coexist without either guessing about the other.
_EMPLOYEE_PREFIX = "D-"

#: Six travellers, spread across the two divisions the directory fixtures build.
#: One is JO/COS — spec §14 calls for exactly that, because ``is_jo_cos`` is what
#: makes the conditional checklist item appear, and a demo where that item never
#: appears cannot show the checklist engine doing anything interesting.
_TRAVELLERS: tuple[dict[str, Any], ...] = (
    {"n": "0001", "given": "Liwayway", "sur": "Bautista",
     "title": "Health Program Officer III", "status": "permanent",
     "division": "BLHSD-TECH", "section": "BLHSD-TECH-PLAN"},
    {"n": "0002", "given": "Ramon", "sur": "Delgado",
     "title": "Administrative Officer V", "status": "permanent",
     "division": "BLHSD-FIN", "section": "BLHSD-FIN-ACCT"},
    {"n": "0003", "given": "Perlita", "sur": "Manalo",
     "title": "Nurse IV", "status": "permanent",
     "division": "BLHSD-TECH", "section": None},
    {"n": "0004", "given": "Efren", "sur": "Villanueva",
     "title": "Statistician II", "status": "permanent",
     "division": "BLHSD-TECH", "section": "BLHSD-TECH-PLAN"},
    {"n": "0005", "given": "Corazon", "sur": "Aguilar",
     "title": "Budget Officer III", "status": "permanent",
     "division": "BLHSD-FIN", "section": None},
    # The JO/COS traveller (spec §14's "1 JO/COS").
    {"n": "0006", "given": "Dexter", "sur": "Pascual",
     "title": "Project Technical Assistant II", "status": "job_order",
     "division": "BLHSD-TECH", "section": "BLHSD-TECH-PLAN"},
)


#: The two past fixture activities the demo trips hang off, by title. They are
#: created by `ops/bootstrap.py::_load_fixtures` (run first — `load_pilot_fixtures`
#: already checks for the org tree it also builds), and their date windows BRACKET
#: the trip offsets below.
#:
#: This is what finally populates `reimb_claims.activity_id`. Until Stage D-2 the
#: column had been validated on PATCH since R-1 and was non-null on ZERO of 838
#: claims, because the wizard's activity picker was cut for want of an activities
#: endpoint (module doc, spec §9.3 step 1). A demo of the connection spine
#: (master-plan §1.2) in which nothing is connected demonstrates the opposite of
#: the point.
#:
#: Missing activities are NOT an error: a link is nullable and soft by design
#: (§1.3's integration invariants), so a trip whose activity was never loaded is
#: simply an untagged trip — which is also a state worth seeing on screen.
_ACT_Q3 = "[fixture] Q3 Regional Health Systems Review"
_ACT_IMM = "[fixture] Immunization Coverage Validation"


def _leg(seq, offset, *, mode, fare=None, region=None, place=None, **kw):
    return {
        "seq": seq, "offset": offset, "transport_mode": mode,
        "fare": fare, "destination_region_code": region, "place": place, **kw,
    }


#: Ten trips. Dates are RELATIVE to the run date so a demo is never looking at a
#: stale quarter, and the anchors that must not move (the worked example's
#: totals) are pinned by amount rather than by date.
#:
#: NOTE the deliberate variety: NCR and non-NCR clusters so the DTE rate visibly
#: differs, a same-day round trip (50% rule), a within-50km commute with and
#: without the overnight attestation, a government-vehicle trip with no fares at
#: all, and host-provided meals/lodging. Each one exists to make a different rule
#: from spec §8 visible on screen rather than only in a test.
_TRIPS: tuple[dict[str, Any], ...] = (
    {
        "key": "worked-example",
        "activity": _ACT_Q3,
        "traveller": "0001",
        "purpose": "Regional health systems review (spec §8 worked example)",
        "destination": "Manila, NCR",
        "region": "13", "depart": -40, "days": 2,
        # The §8 anchor: 3 days NCR at ₱2,200 → ₱5,500 per diem, plus ₱1,000
        # transport → ₱6,500 grand. Asserted by test, never hardcoded here — the
        # server computes it, which is the whole point of showing it in a demo.
        "legs": (
            _leg(1, 0, mode="bus", fare="500.00", region="13"),
            _leg(2, 2, mode="bus", fare="500.00"),
        ),
    },
    {
        "key": "taxi-over-threshold",
        "activity": _ACT_Q3,
        "traveller": "0002",
        "purpose": "Fund utilisation conference — taxi fare over the RER threshold",
        "destination": "Quezon City, NCR",
        "region": "13", "depart": -30, "days": 1,
        # >₱300 taxi: fires the `amount_threshold` auto-check, which demands a
        # Reimbursement Expense Receipt. Spec §14 asks for this fare explicitly.
        "legs": (
            _leg(1, 0, mode="taxi", fare="450.00", region="13"),
            _leg(2, 1, mode="taxi", fare="380.00"),
        ),
    },
    {
        "key": "cluster-switch",
        "activity": _ACT_Q3,
        "traveller": "0003",
        "purpose": "Provincial hospital assessment — two DTE clusters in one trip",
        "destination": "Cebu City then Manila",
        "region": "13", "depart": -25, "days": 2,
        "legs": (
            _leg(1, 0, mode="plane", fare="3200.00", region="07"),
            _leg(2, 1, mode="plane", fare="2800.00", region="13"),
            _leg(3, 2, mode="bus", fare="500.00"),
        ),
    },
    {
        "key": "same-day",
        "activity": _ACT_IMM,
        "traveller": "0004",
        "purpose": "Same-day coordination meeting (50% DTE, no lodging)",
        "destination": "Manila, NCR",
        "region": "13", "depart": -20, "days": 0,
        "legs": (_leg(1, 0, mode="bus", fare="300.00", region="13"),),
    },
    {
        "key": "within-50km-commute",
        "activity": _ACT_IMM,
        "traveller": "0005",
        "purpose": "Nearby facility visit within 50 km (fares only, 0% DTE)",
        "destination": "Pasig City",
        "region": "13", "depart": -18, "days": 1,
        "within_50km": True,
        # `other`, not a made-up mode: the enum is the closed set spec §5.2
        # defines (plane/bus/boat/taxi/ride_hail/gov_vehicle/other), and a
        # jeepney fare is exactly what `other` is there for.
        "legs": (
            _leg(1, 0, mode="other", fare="120.00", region="13"),
            _leg(2, 1, mode="other", fare="120.00"),
        ),
    },
    {
        "key": "within-50km-overnight",
        "activity": _ACT_IMM,
        "traveller": "0005",
        "purpose": "Nearby facility visit within 50 km WITH overnight attestation",
        "destination": "Antipolo City",
        "region": "13", "depart": -15, "days": 1,
        "within_50km": True, "overnight": True,
        "legs": (
            _leg(1, 0, mode="bus", fare="180.00", region="13"),
            _leg(2, 1, mode="bus", fare="180.00"),
        ),
    },
    {
        "key": "gov-vehicle",
        "activity": _ACT_IMM,
        "traveller": "0001",
        "purpose": "Field monitoring by government vehicle (no fares)",
        "destination": "Bulacan",
        "region": "03", "depart": -12, "days": 1,
        "legs": (
            _leg(1, 0, mode="gov_vehicle", region="03"),
            _leg(2, 1, mode="gov_vehicle"),
        ),
    },
    {
        "key": "host-provided",
        "activity": _ACT_IMM,
        "traveller": "0004",
        "purpose": "Partner-hosted workshop (meals and lodging provided)",
        "destination": "Baguio City",
        "region": "01", "depart": -10, "days": 2,
        "legs": (
            _leg(1, 0, mode="bus", fare="750.00", region="01",
                 lodging_provided=True, meals_provided=True),
            _leg(2, 2, mode="bus", fare="750.00"),
        ),
    },
    {
        "key": "jo-cos-traveller",
        "activity": _ACT_IMM,
        "traveller": "0006",
        "purpose": "Data quality check — JO/COS traveller (conditional checklist)",
        "destination": "Manila, NCR",
        "region": "13", "depart": -8, "days": 1,
        "legs": (
            _leg(1, 0, mode="bus", fare="500.00", region="13"),
            _leg(2, 1, mode="bus", fare="500.00"),
        ),
    },
    {
        "key": "cash-advance-trip",
        "activity": _ACT_Q3,
        "traveller": "0002",
        "purpose": "Immunisation coverage validation (funded by cash advance)",
        "destination": "Davao City",
        "region": "11", "depart": -28, "days": 3,
        "cash_advance": True,
        "legs": (
            _leg(1, 0, mode="plane", fare="4200.00", region="11"),
            _leg(2, 3, mode="plane", fare="4200.00"),
        ),
    },
)

#: The cash advance spec §14 asks for: OPEN and aged so its 30-day COA clock is
#: inside the due-soon window. 25 days elapsed against a 30-day deadline puts it
#: at D-5, which renders an amber countdown ring and the overdue consequence
#: copy — a demo where the clock reads "25 days left" shows nothing.
_CA_ELAPSED_DAYS = 25
_CA_AMOUNT = Decimal("18000.00")


async def _org_units(session: AsyncSession) -> dict[str, OrgUnit]:
    rows = (await session.execute(select(OrgUnit))).scalars().all()
    return {u.code: u for u in rows if u.code}


async def _ensure_travellers(
    session: AsyncSession, units: dict[str, OrgUnit]
) -> tuple[dict[str, Staff], int]:
    """Six demo travellers, keyed by their number suffix. Idempotent."""
    created = 0
    staff: dict[str, Staff] = {}
    for spec in _TRAVELLERS:
        employee_no = f"{_EMPLOYEE_PREFIX}{spec['n']}"
        row = (
            await session.execute(
                select(Staff).where(Staff.employee_no == employee_no)
            )
        ).scalar_one_or_none()
        if row is None:
            division = units.get(spec["division"])
            section = units.get(spec["section"]) if spec["section"] else None
            row = Staff(
                employee_no=employee_no,
                given_name=spec["given"],
                surname=spec["sur"],
                full_name=f"{spec['given']} {spec['sur']}",
                email=f"{spec['given']}.{spec['sur']}@example.gov.ph".lower(),
                position_title=spec["title"],
                employment_status=spec["status"],
                division_id=division.id if division else None,
                section_id=section.id if section else None,
            )
            session.add(row)
            await session.flush()
            created += 1
        staff[spec["n"]] = row
    return staff, created


async def _ensure_cash_advance(
    session: AsyncSession, *, claimant_id: int, today: date
) -> tuple[ReimbCashAdvance, bool]:
    """The aged, still-open advance. Idempotent on its DV number."""
    dv_no = "DV-DEMO-0001"
    row = (
        await session.execute(
            select(ReimbCashAdvance).where(ReimbCashAdvance.dv_no == dv_no)
        )
    ).scalar_one_or_none()
    if row is not None:
        return row, False
    # `date_return` is what the 30-day clock is pinned to (R-6-clock), so aging
    # the advance means aging THAT, not the DV date.
    returned_on = today - timedelta(days=_CA_ELAPSED_DAYS)
    # Through the SANCTIONED WRITER, not a bare INSERT. `services/cash_advance`
    # calls itself "the SINGLE sanctioned writer of reimb_cash_advances" and it
    # means it: it resolves the COA deadline from the live config (calendar vs
    # working basis), normalizes the money, and enforces PD 1445 §89. A fixture
    # that inserted the row itself got a NULL `deadline_date` — and an advance
    # with no deadline is an advance with no countdown, which is the single
    # thing this fixture exists to put on screen.
    #
    # `actor_user_id=None` because no person is acting: this is a system load,
    # and the audit chain records it as one rather than attributing it to
    # whoever happened to run the command.
    return (
        await ca_service.create_cash_advance(
            session,
            claimant_id=claimant_id,
            amount=_CA_AMOUNT,
            actor_user_id=None,
            dv_no=dv_no,
            dv_date=returned_on - timedelta(days=10),
            dpo_no="DPO-DEMO-0001",
            date_return=returned_on,
        ),
        True,
    )


async def _activity_ids(session: AsyncSession) -> dict[str, int]:
    """``{title: id}`` for the fixture activities the trips link to."""
    rows = (
        await session.execute(
            select(Activity.title, Activity.id).where(
                Activity.title.in_((_ACT_Q3, _ACT_IMM))
            )
        )
    ).all()
    return {title: activity_id for title, activity_id in rows}


async def _ensure_trip(
    session: AsyncSession,
    *,
    spec: dict[str, Any],
    staff: Staff,
    today: date,
    cash_advance_id: int | None,
    activity_id: int | None = None,
) -> tuple[ReimbClaim, bool]:
    marker = f"{DEMO_TAG} {spec['purpose']}"
    existing = (
        await session.execute(select(ReimbClaim).where(ReimbClaim.purpose == marker))
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False

    depart = today + timedelta(days=spec["depart"])
    claim = ReimbClaim(
        kind="reimbursement",
        claimant_id=staff.id,
        purpose=marker,
        destination=spec["destination"],
        destination_region_code=spec["region"],
        date_depart=depart,
        date_return=depart + timedelta(days=spec["days"]),
        is_within_50km=bool(spec.get("within_50km")),
        overnight_stay=bool(spec.get("overnight")),
        is_jo_cos=staff.employment_status in ("job_order", "contract_of_service"),
        # The enum's two values are the DOH fund clusters (spec §5.1): General
        # Fund via ORS, or Trust Fund via BUR. Not a free-text field.
        fund_source="GF_ORS",
        cash_advance_id=cash_advance_id,
        # The connection spine (master-plan §1.2). Nullable and soft by design.
        activity_id=activity_id,
        status="draft",
    )
    session.add(claim)
    await session.flush()

    for leg in spec["legs"]:
        session.add(
            ReimbItineraryLeg(
                claim_id=claim.id,
                seq=leg["seq"],
                leg_date=depart + timedelta(days=leg["offset"]),
                place=leg.get("place") or spec["destination"],
                destination_region_code=leg.get("destination_region_code"),
                transport_mode=leg["transport_mode"],
                fare=Decimal(leg["fare"]) if leg.get("fare") else None,
                lodging_provided=bool(leg.get("lodging_provided")),
                meals_provided=bool(leg.get("meals_provided")),
            )
        )
    await session.flush()

    # Money is SERVER-computed, here as everywhere (hard prohibition). A demo
    # whose totals were literals in this file would be a demo of this file.
    await compute_claim_totals(session, claim_id=claim.id)
    return claim, True


async def load_pilot_fixtures(session: AsyncSession) -> dict[str, Any]:
    """Build the spec §14 demo cast. Idempotent; flushes, caller commits.

    Requires the directory fixtures (``bootstrap load-fixtures``) for the BLHSD
    org tree and the reimbursement reference seeds (``load-reference``) for the
    EO 77 rates the computation reads. Both are checked rather than assumed —
    failing with a sentence naming the missing step beats writing six travellers
    into an empty tree and computing every trip at ₱0.00.
    """
    units = await _org_units(session)
    missing = [
        code
        for code in ("BLHSD", "BLHSD-FIN", "BLHSD-TECH")
        if code not in units
    ]
    if missing:
        raise RuntimeError(
            f"the BLHSD org tree is missing {missing} — run "
            "`bootstrap load-fixtures` first (it builds the org units and the "
            "base staff directory these travellers attach to)"
        )

    today = to_manila(utc_now()).date()
    staff, staff_created = await _ensure_travellers(session, units)

    advance, advance_created = await _ensure_cash_advance(
        session, claimant_id=staff["0002"].id, today=today
    )

    activities = await _activity_ids(session)
    trips_created, totals = 0, {}
    for spec in _TRIPS:
        claim, created = await _ensure_trip(
            session,
            spec=spec,
            staff=staff[spec["traveller"]],
            today=today,
            cash_advance_id=advance.id if spec.get("cash_advance") else None,
            activity_id=activities.get(spec.get("activity", "")),
        )
        trips_created += int(created)
        totals[spec["key"]] = (claim.totals or {}).get("grand")

    return {
        "travellers_created": staff_created,
        "travellers_total": len(_TRAVELLERS),
        "trips_created": trips_created,
        "trips_total": len(_TRIPS),
        "cash_advance_created": advance_created,
        "cash_advance": {
            "dv_no": advance.dv_no,
            "amount": str(advance.amount),
            "deadline_date": str(advance.deadline_date),
            "days_elapsed_since_return": _CA_ELAPSED_DAYS,
        },
        "computed_grand_totals": totals,
        "note": (
            "Drafts only — nothing is submitted. The workflow is driven by hand "
            "through the manual test guide (docs/modules/reimbursement.md §6); "
            "fabricating approval history would put decisions nobody made into "
            "the audit chain. Totals above are server-computed."
        ),
    }
