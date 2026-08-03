"""R-4-app QA gate: acting on a submitted claim + the work-management invariants.

Spec §14 R-4 gate lines proven here: NO NULL HOLDERS across every transition
(the property walk), return requires a reason, returns never orphan, the
next-action copy is verbatim §6.1, segregation blocks the chief approving
their own claim (via the ``User.staff_id`` bridge), and cancel semantics.
"""

import pytest
from sqlalchemy import select

from office_connect.core.api.errors import APIError
from office_connect.modules.reimbursement.models import (
    ReimbReturnEvent,
    ReimbStatusHistory,
)
from office_connect.modules.reimbursement.services import status as st
from office_connect.modules.reimbursement.services.lifecycle import (
    cancel_draft_claim,
    claim_action,
    submit_claim,
)
from tests.reimb_lifecycle_helpers import (
    assert_holder_invariant,
    return_reason_ids,
    standard_cast,
    trip_claim,
)
from tests.workflow_helpers import grant_scoped_role


async def _submitted(app_session, make_user):
    cast = await standard_cast(app_session, make_user)
    await submit_claim(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.owner.id
    )
    return cast


async def test_happy_walk_no_null_holders(app_session, seed_rbac, make_user, reimb_flag_on):
    """draft → division_approval → admin_review → handed_to_fms → paid_closed,
    asserting the §7.1 holder invariant and the §6.1 next-action copy at every
    stop."""
    cast = await _submitted(app_session, make_user)
    claim = cast.claim
    assert_holder_invariant(claim)
    assert claim.next_action == "Approve or return"

    await claim_action(
        app_session, claim_id=claim.id, action="approve",
        actor_user_id=cast.approver.id,
    )
    assert claim.status == st.ADMIN_REVIEW
    assert (claim.holder_kind, claim.holder_id) == ("user", cast.admin.id)
    assert claim.next_action == "Final check & print packet"
    assert_holder_invariant(claim)

    await claim_action(
        app_session, claim_id=claim.id, action="approve",
        actor_user_id=cast.admin.id,
    )
    assert claim.status == st.HANDED_TO_FMS
    assert (claim.holder_kind, claim.holder_id) == ("external_fms", None)
    assert claim.next_action == "Waiting on FMS — update status"
    assert_holder_invariant(claim)

    await claim_action(
        app_session, claim_id=claim.id, action="approve",
        actor_user_id=cast.admin.id,
    )
    assert claim.status == st.PAID_CLOSED
    assert_holder_invariant(claim)  # terminal: holder + next_action cleared

    history = (
        await app_session.execute(
            select(ReimbStatusHistory)
            .where(ReimbStatusHistory.claim_id == claim.id)
            .order_by(ReimbStatusHistory.id)
        )
    ).scalars().all()
    assert [(h.from_status, h.to_status) for h in history] == [
        (st.DRAFT, st.DIVISION_APPROVAL),
        (st.DIVISION_APPROVAL, st.ADMIN_REVIEW),
        (st.ADMIN_REVIEW, st.HANDED_TO_FMS),
        (st.HANDED_TO_FMS, st.PAID_CLOSED),
    ]  # one row per REAL move — no same-state noise


async def test_return_paths_never_orphan(app_session, seed_rbac, make_user, reimb_flag_on):
    """Every return loop lands the ball with a person (spec §7.6)."""
    cast = await _submitted(app_session, make_user)
    claim = cast.claim
    reasons = await return_reason_ids(app_session)

    # division_approval ─return→ returned (holder = claimant)
    await claim_action(
        app_session, claim_id=claim.id, action="return",
        actor_user_id=cast.approver.id, comment="Fix the itinerary.",
        reason_ids=reasons,
    )
    assert claim.status == st.RETURNED
    assert (claim.holder_kind, claim.holder_id) == ("user", cast.owner.id)
    assert claim.next_action == "Fix and resubmit"
    assert_holder_invariant(claim)

    # returned ─resubmit→ division_approval ─approve→ admin_review ─return→ returned
    await claim_action(app_session, claim_id=claim.id, action="resubmit", actor_user_id=cast.owner.id)
    await claim_action(app_session, claim_id=claim.id, action="approve", actor_user_id=cast.approver.id)
    await claim_action(
        app_session, claim_id=claim.id, action="return",
        actor_user_id=cast.admin.id, comment="CENRR missing.",
        reason_ids=reasons,
    )
    assert claim.status == st.RETURNED
    assert_holder_invariant(claim)

    # …to FMS and back: handed_to_fms ─return→ fms_returned (holder = Admin
    # Officer, the relay) ─return→ returned (holder = claimant).
    await claim_action(app_session, claim_id=claim.id, action="resubmit", actor_user_id=cast.owner.id)
    await claim_action(app_session, claim_id=claim.id, action="approve", actor_user_id=cast.approver.id)
    await claim_action(app_session, claim_id=claim.id, action="approve", actor_user_id=cast.admin.id)
    await claim_action(
        app_session, claim_id=claim.id, action="return",
        actor_user_id=cast.admin.id, comment="ORS number mismatch.",
        reason_ids=reasons,
    )
    assert claim.status == st.FMS_RETURNED
    assert (claim.holder_kind, claim.holder_id) == ("user", cast.admin.id)
    assert claim.next_action == "Relay FMS comments"
    assert_holder_invariant(claim)

    await claim_action(
        app_session, claim_id=claim.id, action="return",
        actor_user_id=cast.admin.id, comment="Per FMS: correct the ORS number.",
        reason_ids=reasons,
    )
    assert claim.status == st.RETURNED
    assert (claim.holder_kind, claim.holder_id) == ("user", cast.owner.id)
    assert_holder_invariant(claim)


async def test_return_requires_reason(app_session, seed_rbac, make_user, reimb_flag_on):
    """Two independent mandates, both server-side (R-4-screens closed the
    delta-row-44 deferral): ≥1 taxonomy reason (spec §5.6, the module) AND a
    free comment (``requires_comment``, the engine)."""
    cast = await _submitted(app_session, make_user)

    with pytest.raises(APIError) as ei:
        await claim_action(
            app_session, claim_id=cast.claim.id, action="return",
            actor_user_id=cast.approver.id, comment="No reason picked.",
        )
    assert ei.value.code == "reimb_return_reason_required"
    await app_session.rollback()

    cast = await _submitted(app_session, make_user)
    with pytest.raises(APIError) as ei:
        await claim_action(
            app_session, claim_id=cast.claim.id, action="return",
            actor_user_id=cast.approver.id,
            reason_ids=await return_reason_ids(app_session),
        )
    assert ei.value.code == "workflow_comment_required"
    await app_session.rollback()


async def test_return_rejects_reasons_outside_the_live_taxonomy(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    """``reason_ids`` is FK-less JSONB — the service is the only thing keeping
    junk out of the R-8 learning loop."""
    cast = await _submitted(app_session, make_user)
    good = await return_reason_ids(app_session)
    with pytest.raises(APIError) as ei:
        await claim_action(
            app_session, claim_id=cast.claim.id, action="return",
            actor_user_id=cast.approver.id, comment="Missing DPO copy.",
            reason_ids=[*good, 987654],
        )
    assert ei.value.code == "reimb_unknown_return_reason"
    assert "987654" in ei.value.message
    await app_session.rollback()


async def test_return_writes_return_event(app_session, seed_rbac, make_user, reimb_flag_on):
    cast = await _submitted(app_session, make_user)
    reasons = await return_reason_ids(app_session, "MISSING_OR", "PER_DIEM_CALC")
    await claim_action(
        app_session, claim_id=cast.claim.id, action="return",
        actor_user_id=cast.approver.id, comment="Missing DPO copy.",
        reason_ids=reasons,
    )
    event = (
        await app_session.execute(
            select(ReimbReturnEvent).where(
                ReimbReturnEvent.claim_id == cast.claim.id
            )
        )
    ).scalar_one()
    assert event.step_id is not None  # the gate step returned from
    assert event.reason_ids == reasons
    assert event.free_comment == "Missing DPO copy."
    assert event.returned_to == "claimant"


async def test_replayed_return_does_not_append_a_second_return_event(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    """``execute_action`` replays the original event verbatim on an idempotency
    hit; the module's return-event insert must ride the same replay guard, or a
    double-tapped Return would fabricate a second entry in an APPEND-ONLY,
    hash-chained table."""
    cast = await _submitted(app_session, make_user)
    reasons = await return_reason_ids(app_session)
    for _ in range(2):
        await claim_action(
            app_session, claim_id=cast.claim.id, action="return",
            actor_user_id=cast.approver.id, comment="Fix the fare.",
            reason_ids=reasons, idempotency_key="return-once",
        )
    events = (
        (
            await app_session.execute(
                select(ReimbReturnEvent).where(
                    ReimbReturnEvent.claim_id == cast.claim.id
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 1
    history = (
        (
            await app_session.execute(
                select(ReimbStatusHistory).where(
                    ReimbStatusHistory.claim_id == cast.claim.id,
                    ReimbStatusHistory.to_status == st.RETURNED,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(history) == 1  # the two append-only lanes stay 1:1


async def test_segregation_blocks_chief_approving_own_claim(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    """The routine COA case: a Division Chief files their own travel. The
    chief holds approve for their division — segregation (maker == checker)
    must 409, and holder resolution must already have picked someone else."""
    from tests.reimbursement_helpers import make_staff

    cast = await standard_cast(app_session, make_user)
    # One person: staff row + login + division-scoped approve (the chief).
    staff = await make_staff(app_session, division_id=cast.division.id)
    chief, _ = await make_user(staff_id=staff.id)
    await grant_scoped_role(
        app_session, user=chief, role_code="approver", org_unit_id=cast.division.id
    )
    claim = await trip_claim(app_session, staff=staff)

    submitted = await submit_claim(
        app_session, claim_id=claim.id, actor_user_id=chief.id
    )
    # Holder resolution excluded the originator — the OTHER approver holds it.
    assert submitted.holder_id == cast.approver.id

    with pytest.raises(APIError) as ei:
        await claim_action(
            app_session, claim_id=claim.id, action="approve",
            actor_user_id=chief.id,
        )
    assert ei.value.code == "segregation_of_duties"
    await app_session.rollback()


async def test_cancel_from_returned_owner_only_reason_mandatory(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    cast = await _submitted(app_session, make_user)
    await claim_action(
        app_session, claim_id=cast.claim.id, action="return",
        actor_user_id=cast.approver.id, comment="Wrong fund source.",
        reason_ids=await return_reason_ids(app_session),
    )

    outsider, _ = await make_user(roles=("staff",))
    with pytest.raises(APIError) as ei:
        await claim_action(
            app_session, claim_id=cast.claim.id, action="cancel",
            actor_user_id=outsider.id, comment="Nope.",
        )
    assert ei.value.code == "reimb_not_claim_owner"

    with pytest.raises(APIError) as ei:
        await claim_action(
            app_session, claim_id=cast.claim.id, action="cancel",
            actor_user_id=cast.owner.id,
        )
    assert ei.value.code == "workflow_comment_required"

    claim = await claim_action(
        app_session, claim_id=cast.claim.id, action="cancel",
        actor_user_id=cast.owner.id, comment="Trip did not push through.",
    )
    assert claim.status == st.CANCELLED
    assert_holder_invariant(claim)


async def test_cancel_draft_is_module_level(app_session, seed_rbac, make_user, reimb_flag_on):
    """Pre-submit there is no instance — the module chokepoint still owns the
    status write (never scattered code)."""
    cast = await standard_cast(app_session, make_user)

    with pytest.raises(APIError):
        await cancel_draft_claim(
            app_session, claim_id=cast.claim.id, actor_user_id=cast.owner.id,
            comment="",
        )

    claim = await cancel_draft_claim(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.owner.id,
        comment="Filed twice by mistake.",
    )
    assert claim.status == st.CANCELLED
    assert claim.workflow_instance_id is None
    history = (
        await app_session.execute(
            select(ReimbStatusHistory).where(
                ReimbStatusHistory.claim_id == claim.id
            )
        )
    ).scalar_one()
    assert (history.from_status, history.to_status) == (st.DRAFT, st.CANCELLED)


async def test_terminal_claims_refuse_further_actions(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    cast = await _submitted(app_session, make_user)
    for actor in (cast.approver, cast.admin, cast.admin):
        await claim_action(
            app_session, claim_id=cast.claim.id, action="approve",
            actor_user_id=actor.id,
        )
    assert cast.claim.status == st.PAID_CLOSED

    with pytest.raises(APIError) as ei:
        await claim_action(
            app_session, claim_id=cast.claim.id, action="approve",
            actor_user_id=cast.admin.id,
        )
    assert ei.value.code == "workflow_state_conflict"
    await app_session.rollback()
