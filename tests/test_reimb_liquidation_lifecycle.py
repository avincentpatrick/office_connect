"""R-6-liq-chain QA gate: starting a liquidation and walking it to settled.

R-6-clock built the question (an advance with a pinned COA 30-day deadline);
this is the answer. Covered here: the create-from-advance guards, that submit
routes onto the OTHER chain with the OTHER number series, the whole
draft → certify_b → certify_c → handed_to_fms → settled walk with the §7.1
no-null-holder invariant at every stop, the return loop, and the fact that a
settled liquidation leaves My-Work (the union-terminal trap).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from office_connect.core.api.errors import APIError
from office_connect.core.models import User
from office_connect.modules.reimbursement.models import (
    ReimbCashAdvance,
    ReimbClaim,
    ReimbStatusHistory,
)
from office_connect.modules.reimbursement.seeds import apply_reimbursement_seeds
from office_connect.modules.reimbursement.services import cash_advance as ca
from office_connect.modules.reimbursement.services import checklist
from office_connect.modules.reimbursement.services import liquidation as liq
from office_connect.modules.reimbursement.services import status as st
from office_connect.modules.reimbursement.services.lifecycle import (
    claim_action,
    submit_claim,
)
from office_connect.modules.reimbursement.services.settlement import (
    record_settlement,
)
from tests.reimb_checklist_helpers import satisfy_packet
from tests.reimb_lifecycle_helpers import (
    assert_holder_invariant,
    ensure_reimb_workflow,
    return_reason_ids,
    standard_cast,
)
from tests.reimbursement_helpers import make_leg
from tests.workflow_helpers import grant_scoped_role

UTC = timezone.utc
NOW = datetime(2026, 7, 6, 2, 0, tzinfo=UTC)  # Mon 2026-07-06 10:00 Manila
RETURN = date(2026, 7, 3)
DUE = date(2026, 8, 2)  # 30 calendar days after RETURN
JUL1 = date(2026, 7, 1)


async def _cast_with_advance(app_session, make_user, *, date_return=RETURN):
    """The standard org tree + users, plus a cash advance for the claimant and
    the ``reimb.liquidation.certify`` grant the chain's first gate needs."""
    cast = await standard_cast(app_session, make_user)
    await apply_reimbursement_seeds(app_session)
    await ensure_reimb_workflow(app_session)
    # The approver role carries certify; grant_scoped_role in standard_cast
    # already placed them on the division, so this is the same person the claim
    # chain uses — which is the point: one Director, two kinds of approval.
    advance = await ca.create_cash_advance(
        app_session,
        claimant_id=cast.staff.id,
        amount=Decimal("6000.00"),
        actor_user_id=cast.admin.id,
        dv_no="DV-2026-0007",
        dv_date=date(2026, 6, 25),
        dpo_no="DPO-2026-0042",
        date_return=date_return,
        now=NOW,
    )
    cast.advance = advance
    return cast


async def _liquidation(app_session, cast):
    """A submittable liquidation: started from the advance, given legs and a
    satisfied packet (the liquidation catalog's own blocking set)."""
    claim = await liq.start_liquidation(
        app_session,
        cash_advance_id=cast.advance.id,
        actor_user_id=cast.owner.id,
        now=NOW,
    )
    claim.date_depart = JUL1
    claim.destination_region_code = "13"
    await make_leg(
        app_session, claim_id=claim.id, seq=1, leg_date=JUL1,
        destination_region_code="13", transport_mode="bus", fare="500.00",
    )
    await make_leg(
        app_session, claim_id=claim.id, seq=2, leg_date=claim.date_return,
        transport_mode="bus", fare="500.00",
    )
    await satisfy_packet(app_session, claim=claim, actor_user_id=cast.owner.id)
    await app_session.flush()
    return claim


# --- Starting one ----------------------------------------------------------


async def test_start_links_the_advance_and_starts_its_clock(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    cast = await _cast_with_advance(app_session, make_user)
    claim = await liq.start_liquidation(
        app_session,
        cash_advance_id=cast.advance.id,
        actor_user_id=cast.owner.id,
        now=NOW,
    )

    assert claim.kind == "liquidation"
    assert claim.status == st.DRAFT
    assert claim.claimant_id == cast.staff.id
    # Prefilled from what Accounting already recorded — a traveller cannot know
    # the DV, and retyping the return date would describe a different trip.
    assert claim.dpo_no == "DPO-2026-0042"
    assert claim.date_return == RETURN
    # The link + the deadline MIRROR, which is what makes the tracker's
    # countdown and the seeded deadline_check live from the first read.
    assert claim.cash_advance_id == cast.advance.id
    assert claim.liquidation_deadline == DUE
    # The advance moved on its own axis.
    assert cast.advance.status == ca.LIQUIDATION_STARTED
    # §6.2 row 1 copy, from the LIQUIDATION vocabulary, not the claim one.
    assert claim.next_action == "Complete your liquidation"
    await app_session.rollback()


async def test_only_the_traveller_may_liquidate(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    """Filing IS certification A, and A certifies that the CLAIMANT incurred
    the expenses — an Admin Officer filing on their behalf would put the wrong
    name against a COA certification."""
    cast = await _cast_with_advance(app_session, make_user)
    with pytest.raises(APIError) as ei:
        await liq.start_liquidation(
            app_session,
            cash_advance_id=cast.advance.id,
            actor_user_id=cast.admin.id,
            now=NOW,
        )
    assert ei.value.code == "reimb_not_advance_holder"
    await app_session.rollback()


async def test_one_live_liquidation_per_advance(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    cast = await _cast_with_advance(app_session, make_user)
    first = await liq.start_liquidation(
        app_session, cash_advance_id=cast.advance.id,
        actor_user_id=cast.owner.id, now=NOW,
    )
    with pytest.raises(APIError) as ei:
        await liq.start_liquidation(
            app_session, cash_advance_id=cast.advance.id,
            actor_user_id=cast.owner.id, now=NOW,
        )
    assert ei.value.code == "reimb_liquidation_exists"
    # The error NAMES the existing one, so the button has somewhere to go.
    assert ei.value.details[0]["claim_id"] == first.id
    await app_session.rollback()


async def test_a_cancelled_liquidation_frees_the_advance(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    """``cancelled`` is excluded from the live set on purpose: a mistaken start
    must be re-filable, or the advance is stuck with a dead claim forever."""
    cast = await _cast_with_advance(app_session, make_user)
    first = await liq.start_liquidation(
        app_session, cash_advance_id=cast.advance.id,
        actor_user_id=cast.owner.id, now=NOW,
    )
    from office_connect.modules.reimbursement.services.lifecycle import (
        cancel_draft_claim,
    )

    await cancel_draft_claim(
        app_session, claim_id=first.id, actor_user_id=cast.owner.id,
        comment="Filed against the wrong advance.",
    )
    second = await liq.start_liquidation(
        app_session, cash_advance_id=cast.advance.id,
        actor_user_id=cast.owner.id, now=NOW,
    )
    assert second.id != first.id
    await app_session.rollback()


async def test_a_settled_advance_has_nothing_left_to_liquidate(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    cast = await _cast_with_advance(app_session, make_user)
    cast.advance.status = ca.SETTLED
    await app_session.flush()
    with pytest.raises(APIError) as ei:
        await liq.start_liquidation(
            app_session, cash_advance_id=cast.advance.id,
            actor_user_id=cast.owner.id, now=NOW,
        )
    assert ei.value.code == "reimb_cash_advance_settled"
    await app_session.rollback()


# --- The chain -------------------------------------------------------------


async def test_submit_burns_an_lq_number_not_an_rb(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    cast = await _cast_with_advance(app_session, make_user)
    claim = await _liquidation(app_session, cast)
    await submit_claim(
        app_session, claim_id=claim.id, actor_user_id=cast.owner.id, now=NOW
    )
    assert claim.ref_no.startswith("LQ-2026-")
    assert claim.status == st.CERTIFY_B
    await app_session.rollback()


async def test_the_walk_to_settled_never_orphans(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    """draft → certify_b → certify_c → handed_to_fms → settled, asserting the
    §7.1 holder invariant and the §6.2 next-action copy at every stop."""
    cast = await _cast_with_advance(app_session, make_user)
    claim = await _liquidation(app_session, cast)

    await submit_claim(
        app_session, claim_id=claim.id, actor_user_id=cast.owner.id, now=NOW
    )
    assert_holder_invariant(claim)
    assert claim.status == st.CERTIFY_B
    assert claim.next_action == "Certify or return"

    # Certification B — the Director, on reimb.liquidation.certify.
    await claim_action(
        app_session, claim_id=claim.id, action="approve",
        actor_user_id=cast.approver.id, now=NOW,
    )
    assert_holder_invariant(claim)
    assert claim.status == st.CERTIFY_C
    assert claim.next_action == "Record the Accounting certification"

    # Certification C — the Admin Officer RECORDING the wet signature. The
    # comment is mandatory: it is the only record of C the platform holds.
    with pytest.raises(APIError) as ei:
        await claim_action(
            app_session, claim_id=claim.id, action="approve",
            actor_user_id=cast.admin.id, now=NOW,
        )
    assert ei.value.code == "workflow_comment_required"

    await claim_action(
        app_session, claim_id=claim.id, action="approve",
        actor_user_id=cast.admin.id,
        comment="Signed by the Head, Accounting Unit on 2026-07-08; page filed.",
        now=NOW,
    )
    assert_holder_invariant(claim)
    assert claim.status == st.HANDED_TO_FMS
    assert claim.holder_kind == "external_fms"
    assert claim.holder_id is None

    # The last rung is a MONEY state (R-6-liq-settle). A bare approve refuses,
    # naming the route that does the thing — `settled` asserts the advance is
    # closed, and nothing has closed it.
    with pytest.raises(APIError) as ei:
        await claim_action(
            app_session, claim_id=claim.id, action="approve",
            actor_user_id=cast.admin.id, now=NOW,
        )
    assert ei.value.code == "reimb_settlement_required"

    # ₱6,000 advanced against a ₱6,500 trip → an over-advance: nothing to
    # refund, so no OR is asked for and none may be given.
    await record_settlement(
        app_session, claim_id=claim.id, actor_user_id=cast.admin.id, now=NOW
    )
    assert_holder_invariant(claim)
    assert claim.status == st.SETTLED
    assert claim.holder_kind is None
    assert claim.next_action is None

    history = (
        (
            await app_session.execute(
                select(ReimbStatusHistory)
                .where(ReimbStatusHistory.claim_id == claim.id)
                .order_by(ReimbStatusHistory.id)
            )
        ).scalars().all()
    )
    assert [h.to_status for h in history] == [
        st.DRAFT, st.CERTIFY_B, st.CERTIFY_C, st.HANDED_TO_FMS, st.SETTLED,
    ]
    await app_session.rollback()


async def test_the_claimant_can_clear_neither_certification(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    """COA 92-389 segregation, on both checker slots. The claimant is the maker
    (that IS certification A), so they may never be a checker."""
    cast = await _cast_with_advance(app_session, make_user)
    claim = await _liquidation(app_session, cast)
    await submit_claim(
        app_session, claim_id=claim.id, actor_user_id=cast.owner.id, now=NOW
    )
    # Give the claimant BOTH gate permissions — segregation, not authorization,
    # is what must stop them.
    await grant_scoped_role(
        app_session, user=cast.owner, role_code="approver",
        org_unit_id=cast.division.id,
    )
    await grant_scoped_role(
        app_session, user=cast.owner, role_code="admin_officer",
        org_unit_id=cast.office.id,
    )
    with pytest.raises(APIError) as ei:
        await claim_action(
            app_session, claim_id=claim.id, action="approve",
            actor_user_id=cast.owner.id, now=NOW,
        )
    assert ei.value.code == "segregation_of_duties"
    await app_session.rollback()


async def test_a_returned_liquidation_recertifies_from_the_top(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    cast = await _cast_with_advance(app_session, make_user)
    claim = await _liquidation(app_session, cast)
    await submit_claim(
        app_session, claim_id=claim.id, actor_user_id=cast.owner.id, now=NOW
    )
    await claim_action(
        app_session, claim_id=claim.id, action="approve",
        actor_user_id=cast.approver.id, now=NOW,
    )
    assert claim.status == st.CERTIFY_C

    await claim_action(
        app_session, claim_id=claim.id, action="return",
        actor_user_id=cast.admin.id, comment="The OR for the hotel is missing.",
        reason_ids=await return_reason_ids(app_session, "MISSING_OR"), now=NOW,
    )
    assert claim.status == st.RETURNED
    assert claim.next_action == "Fix and resubmit"
    ref_before = claim.ref_no

    await claim_action(
        app_session, claim_id=claim.id, action="resubmit",
        actor_user_id=cast.owner.id, now=NOW,
    )
    # Back at B, not at C: B never inherits a decision made about the version
    # C bounced. The number is never reissued.
    assert claim.status == st.CERTIFY_B
    assert claim.ref_no == ref_before
    await app_session.rollback()


async def test_a_settled_liquidation_leaves_my_work(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    """The union-terminal trap, pinned end to end: My-Work filters on
    ``ALL_TERMINAL_STATES`` because its query spans both kinds, so a ``settled``
    missing from that union would leave every finished liquidation in the
    claimant's inbox forever."""
    cast = await _cast_with_advance(app_session, make_user)
    claim = await _liquidation(app_session, cast)
    await submit_claim(
        app_session, claim_id=claim.id, actor_user_id=cast.owner.id, now=NOW
    )
    await claim_action(
        app_session, claim_id=claim.id, action="approve",
        actor_user_id=cast.approver.id, now=NOW,
    )
    await claim_action(
        app_session, claim_id=claim.id, action="approve",
        actor_user_id=cast.admin.id, comment="Wet signature recorded.", now=NOW,
    )
    await record_settlement(
        app_session, claim_id=claim.id, actor_user_id=cast.admin.id, now=NOW
    )
    assert claim.status == st.SETTLED

    rows = (
        (
            await app_session.execute(
                select(ReimbClaim).where(
                    ReimbClaim.claimant_id == cast.staff.id,
                    ReimbClaim.status.not_in(st.ALL_TERMINAL_STATES),
                )
            )
        ).scalars().all()
    )
    assert claim.id not in {r.id for r in rows}
    await app_session.rollback()


# --- The catalog + the first seeded deadline_check --------------------------


async def test_the_liquidation_catalog_is_its_own_set(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    cast = await _cast_with_advance(app_session, make_user)
    claim = await liq.start_liquidation(
        app_session, cash_advance_id=cast.advance.id,
        actor_user_id=cast.owner.id, now=NOW,
    )
    view = await checklist.checklist_view(app_session, claim=claim)
    codes = {row.plan.catalog.code for row in view.rows}
    assert {"TO-01", "CTC-47", "OR-01", "LIQ-30", "LR-44"} <= codes
    # Reimbursement-only rows must not leak across kinds.
    assert "IOT-45" not in codes
    assert "DV-32" not in codes

    # CRT-C is seeded {"always": false}: the signed page needs a home, but
    # requiring it would block submit and certification B — demanding the
    # signature before the chain that obtains it has started.
    blocking = {b.code for b in view.status.blocking}
    assert "CRT-C" not in blocking
    # data_only and generated_doc never block (delta row 67).
    assert "LIQ-30" not in blocking
    assert "LR-44" not in blocking
    assert {"TO-01", "CTC-47", "OR-01"} == blocking
    await app_session.rollback()


async def test_the_seeded_deadline_check_passes_then_flags(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    """The first seeded ``deadline_check`` — registered inert at R-3, given its
    substrate at R-6-clock, given its RULE here. It must flag a late filing
    without ever blocking it: a late traveller must not be trapped unable to
    file the very liquidation that ends the lateness."""
    cast = await _cast_with_advance(app_session, make_user)
    claim = await liq.start_liquidation(
        app_session, cash_advance_id=cast.advance.id,
        actor_user_id=cast.owner.id, now=NOW,
    )

    def _liq30(view):
        return next(r for r in view.rows if r.plan.catalog.code == "LIQ-30")

    # Well inside the 30 days (NOW = 2026-07-06, DUE = 2026-08-02).
    view = await checklist.checklist_view(app_session, claim=claim, now=NOW)
    checks = _liq30(view).plan.checks
    assert [c.outcome for c in checks] == ["passed"]
    assert checks[0].reason == "within_deadline"
    assert not view.status.flags

    # A day past the deadline.
    late = datetime(2026, 8, 3, 2, 0, tzinfo=UTC)
    view = await checklist.checklist_view(app_session, claim=claim, now=late)
    row = _liq30(view)
    assert [c.outcome for c in row.plan.checks] == ["flagged"]
    assert row.plan.checks[0].reason == "deadline_passed"
    assert row.plan.checks[0].detail["days_late"] == 1
    # Flagged, never blocking (spec §5.3: "a flag never blocks alone").
    assert "LIQ-30" not in {b.code for b in view.status.blocking}
    flagged_catalog_ids = {catalog_id for catalog_id, _ in view.status.flags}
    assert row.plan.catalog.catalog_id in flagged_catalog_ids
    await app_session.rollback()
