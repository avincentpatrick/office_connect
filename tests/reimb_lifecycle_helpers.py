"""Shared builders for the R-4-app lifecycle tests.

The standard cast: an office → division org tree, a claimant staff row IN that
division with a linked login (the ``User.staff_id`` bridge), a division-scoped
approver, an office-scoped Admin Officer, and a manila_3day-shaped trip on the
claimant. Definition + module seeds are ensured idempotently (the suite shares
one published ``reimbursement.claim`` v1 — exactly the production shape).
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from office_connect.modules.reimbursement.seeds import apply_reimbursement_seeds
from office_connect.modules.reimbursement.workflow import ensure_claim_definition
from tests.reimbursement_helpers import make_claim, make_leg, make_staff
from tests.workflow_helpers import grant_scoped_role, make_org_unit

JUL1, JUL3 = date(2026, 7, 1), date(2026, 7, 3)


async def ensure_reimb_workflow(session):
    """Module reference seeds + the published claim definition (idempotent)."""
    await apply_reimbursement_seeds(session)
    version = await ensure_claim_definition(session)
    await session.flush()
    return version


async def trip_claim(session, *, staff, **claim_kw):
    """A manila_3day-shaped trip (grand ₱6,500) on an EXISTING staff row —
    the factory in ``reimbursement_trip_factories`` creates its own staff,
    which here must carry a division for org-unit derivation."""
    claim = await make_claim(
        session,
        claimant_id=staff.id,
        destination_region_code="13",
        date_depart=JUL1,
        date_return=JUL3,
        **claim_kw,
    )
    await make_leg(
        session, claim_id=claim.id, seq=1, leg_date=JUL1,
        destination_region_code="13", transport_mode="bus", fare="500.00",
    )
    await make_leg(
        session, claim_id=claim.id, seq=2, leg_date=JUL3,
        transport_mode="bus", fare="500.00",
    )
    return claim


async def standard_cast(session, make_user):
    """Office → division tree + owner/approver/admin users + a submittable
    claim. Callers needing committed data (separate-session tests) commit."""
    office = await make_org_unit(session, kind="office")
    division = await make_org_unit(session, kind="division", parent=office)

    staff = await make_staff(session, division_id=division.id)
    owner, _ = await make_user(roles=("staff",), staff_id=staff.id)

    approver, _ = await make_user()
    await grant_scoped_role(
        session, user=approver, role_code="approver", org_unit_id=division.id
    )
    admin, _ = await make_user()
    await grant_scoped_role(
        session, user=admin, role_code="admin_officer", org_unit_id=office.id
    )

    await ensure_reimb_workflow(session)
    claim = await trip_claim(session, staff=staff)
    await session.flush()
    return SimpleNamespace(
        office=office, division=division, staff=staff,
        owner=owner, approver=approver, admin=admin, claim=claim,
    )


def assert_holder_invariant(claim) -> None:
    """Spec §7.1 / R-4 QA gate: a holder exists IFF the claim is non-terminal;
    an ``external_fms`` holder legitimately has a NULL id — a ``user`` holder
    never does."""
    from office_connect.modules.reimbursement.services import status as st

    if claim.status in st.TERMINAL_STATES:
        assert claim.holder_kind is None, claim.status
        assert claim.holder_id is None, claim.status
        assert claim.next_action is None, claim.status
    else:
        assert claim.holder_kind is not None, claim.status
        if claim.holder_kind == "user":
            assert claim.holder_id is not None, claim.status
        else:
            assert claim.holder_kind == "external_fms", claim.status
        assert claim.next_action, claim.status
