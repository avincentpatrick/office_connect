"""R-3 — the submit gate and the approve gate (spec §2, §5.3, §9.4).

Spec §2: *"A claim physically cannot be submitted with a missing required
item."* Spec §9.4: *"an approver can approve past a flag (logged) but never past
a missing required item."* Both are enforced here, in the service, so a Celery
job or a shell caller is covered — not only the HTTP dialog.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import func, select

from office_connect.core.api.errors import APIError
from office_connect.core.models import WorkflowInstance
from office_connect.modules.reimbursement.models import ReimbChecklistCatalog
from office_connect.modules.reimbursement.services import (
    checklist,
    claim_action,
    submit_claim,
)
from office_connect.modules.reimbursement.services.actions import claim_actions
from tests.reimb_checklist_helpers import satisfy_packet, tiny_jpeg
from tests.reimb_lifecycle_helpers import return_reason_ids, standard_cast


async def _catalog_id(session, code, *, claim_kind="reimbursement"):
    """The catalog row id for a code — scoped by KIND.

    The natural key is ``(claim_kind, code)`` and R-6-liq-chain gave TO-01 and
    CTC-47 a liquidation twin, so a lookup on ``code`` alone is genuinely
    ambiguous now rather than merely under-specified.
    """
    return (
        await session.execute(
            select(ReimbChecklistCatalog.id).where(
                ReimbChecklistCatalog.code == code,
                ReimbChecklistCatalog.claim_kind == claim_kind,
            )
        )
    ).scalar_one()


# --- submit -----------------------------------------------------------------


async def test_submit_refuses_an_incomplete_packet_and_names_the_blockers(
    make_user, seed_rbac, app_session, reimb_flag_on
):
    cast = await standard_cast(app_session, make_user, packet=False)
    with pytest.raises(APIError) as exc:
        await submit_claim(
            app_session, claim_id=cast.claim.id, actor_user_id=cast.owner.id
        )

    error = exc.value
    assert (error.status_code, error.code) == (422, "reimb_packet_incomplete")
    assert {row["code"] for row in error.details} == {"TO-01", "CTC-47"}
    # Spec §9.1 principle 4 — the message says what to do next, not just "no".
    assert "TO-01" in error.message
    assert "Documents step" in error.message


async def test_a_refused_submit_creates_no_instance_and_burns_no_reference(
    make_user, seed_rbac, app_session, reimb_flag_on
):
    """The reason the gate sits BEFORE ``start_instance``: reference numbers are
    never reused, so an incomplete packet must not consume one."""
    cast = await standard_cast(app_session, make_user, packet=False)
    await app_session.commit()  # so the rollback below discards only the submit
    claim_id = cast.claim.id
    before = (
        await app_session.execute(
            select(func.count()).select_from(WorkflowInstance)
        )
    ).scalar_one()

    with pytest.raises(APIError):
        await submit_claim(
            app_session, claim_id=claim_id, actor_user_id=cast.owner.id
        )
    await app_session.rollback()

    from office_connect.modules.reimbursement.models import ReimbClaim

    claim = (
        await app_session.execute(
            select(ReimbClaim).where(ReimbClaim.id == claim_id)
        )
    ).scalar_one()
    assert claim.ref_no is None
    assert claim.workflow_instance_id is None
    assert (
        await app_session.execute(
            select(func.count()).select_from(WorkflowInstance)
        )
    ).scalar_one() == before


async def test_a_complete_packet_submits_and_snapshots_the_circular_version(
    make_user, seed_rbac, app_session, reimb_flag_on
):
    cast = await standard_cast(app_session, make_user)
    claim = await submit_claim(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.owner.id
    )
    assert claim.status == "division_approval"
    assert claim.ref_no.startswith("RB-")

    view = await checklist.checklist_view(app_session, claim=claim)
    assert view.status.complete is True
    # master-plan §1.1 #7 — items record the circular revision they were
    # checked against, so a later catalog edit cannot rewrite history.
    from office_connect.modules.reimbursement.models import ReimbChecklistItem

    versions = (
        (
            await app_session.execute(
                select(ReimbChecklistItem.circular_version).where(
                    ReimbChecklistItem.claim_id == claim.id
                )
            )
        )
        .scalars()
        .all()
    )
    assert set(versions) == {"COA Circular 2023-004"}


async def test_a_flag_never_blocks_submit(
    make_user, seed_rbac, app_session, reimb_flag_on
):
    """A ₱500 taxi fare trips the CENRR threshold check. Spec §5.3: the claim
    still submits — the flag surfaces to the reviewer instead."""
    from tests.reimbursement_helpers import make_leg

    cast = await standard_cast(app_session, make_user, packet=False)
    await make_leg(
        app_session,
        claim_id=cast.claim.id,
        seq=3,
        leg_date=cast.claim.date_depart,
        transport_mode="taxi",
        fare="500.00",
    )
    await satisfy_packet(app_session, claim=cast.claim, actor_user_id=cast.owner.id)

    view = await checklist.checklist_view(app_session, claim=cast.claim)
    assert [check.reason for _, check in view.status.flags] == [
        "amount_over_threshold"
    ]
    assert view.status.complete is True

    claim = await submit_claim(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.owner.id
    )
    assert claim.status == "division_approval"


async def test_resubmit_re_runs_the_gate_against_the_edited_claim(
    make_user, seed_rbac, app_session, reimb_flag_on
):
    """A return is usually "you're missing a document" — and an edit during the
    fix-up can spawn a NEW conditional item, which must also be satisfied."""
    cast = await standard_cast(app_session, make_user)
    await submit_claim(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.owner.id
    )
    await claim_action(
        app_session,
        claim_id=cast.claim.id,
        action="return",
        actor_user_id=cast.approver.id,
        comment="Attach the lodging receipt.",
        reason_ids=await return_reason_ids(app_session),
    )

    cast.claim.other_total = Decimal("250.00")  # spawns LOD-01
    await app_session.flush()
    with pytest.raises(APIError) as exc:
        await claim_action(
            app_session,
            claim_id=cast.claim.id,
            action="resubmit",
            actor_user_id=cast.owner.id,
        )
    assert exc.value.code == "reimb_packet_incomplete"
    assert {row["code"] for row in exc.value.details} == {"LOD-01"}


# --- approve ----------------------------------------------------------------


async def test_an_approver_may_approve_past_a_flag(
    make_user, seed_rbac, app_session, reimb_flag_on
):
    from tests.reimbursement_helpers import make_leg

    cast = await standard_cast(app_session, make_user, packet=False)
    await make_leg(
        app_session,
        claim_id=cast.claim.id,
        seq=3,
        leg_date=cast.claim.date_depart,
        transport_mode="taxi",
        fare="500.00",
    )
    await satisfy_packet(app_session, claim=cast.claim, actor_user_id=cast.owner.id)
    await submit_claim(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.owner.id
    )

    claim = await claim_action(
        app_session,
        claim_id=cast.claim.id,
        action="approve",
        actor_user_id=cast.approver.id,
    )
    assert claim.status == "admin_review"


async def test_an_approver_may_never_approve_past_a_missing_required_item(
    make_user, seed_rbac, app_session, reimb_flag_on
):
    """Detaching evidence after submit is the realistic route into this state —
    and the approver's remedy (return) stays available throughout."""
    cast = await standard_cast(app_session, make_user)
    await submit_claim(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.owner.id
    )

    catalog_id = await _catalog_id(app_session, "TO-01")
    from office_connect.modules.reimbursement.models import (
        ReimbAttachment,
        ReimbChecklistItem,
    )

    item_id = (
        await app_session.execute(
            select(ReimbChecklistItem.id).where(
                ReimbChecklistItem.claim_id == cast.claim.id,
                ReimbChecklistItem.catalog_id == catalog_id,
            )
        )
    ).scalar_one()
    join = (
        await app_session.execute(
            select(ReimbAttachment).where(
                ReimbAttachment.checklist_item_id == item_id
            )
        )
    ).scalar_one()
    from office_connect.modules.reimbursement.services import attachments as evidence

    await evidence.remove_claim_evidence(
        app_session, join=join, actor_user_id=cast.owner.id
    )

    with pytest.raises(APIError) as exc:
        await claim_action(
            app_session,
            claim_id=cast.claim.id,
            action="approve",
            actor_user_id=cast.approver.id,
        )
    assert exc.value.code == "reimb_packet_incomplete"
    assert "Return the claim" in exc.value.message  # the approver's own remedy

    verbs = await claim_actions(
        app_session, claim=cast.claim, actor_user_id=cast.approver.id
    )
    assert "approve" not in verbs  # never offer a button certain to 422
    assert "return" in verbs  # …but never strand them either


async def test_approving_does_not_re_materialize_the_packet(
    make_user, seed_rbac, app_session, reimb_flag_on
):
    """workflow-standards §9 — "in-flight always finishes". Facts that change
    after submit must not retroactively block a claim already in the chain: the
    submit-time materialization IS the snapshot.

    Probed through the claim's own facts rather than the shared catalog, so the
    test leaves no row behind for its neighbours to trip over.
    """
    cast = await standard_cast(app_session, make_user)
    await submit_claim(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.owner.id
    )

    # Flipping JO/COS would spawn JO-01 — a brand-new unsatisfied upload item —
    # if anything on the approve path re-evaluated the rules.
    cast.claim.is_jo_cos = True
    await app_session.flush()
    fresh = await checklist.checklist_view(app_session, claim=cast.claim)
    assert "JO-01" in {b.code for b in fresh.status.blocking}  # a fresh look blocks…

    claim = await claim_action(
        app_session,
        claim_id=cast.claim.id,
        action="approve",
        actor_user_id=cast.approver.id,
    )
    assert claim.status == "admin_review"  # …but the approve path does not look


async def test_the_gate_never_blocks_a_return_or_a_cancel(
    make_user, seed_rbac, app_session, reimb_flag_on
):
    """Blocking a RETURN on an incomplete packet would trap the claim in the
    chain — the exact opposite of what the rule is for."""
    cast = await standard_cast(app_session, make_user)
    await submit_claim(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.owner.id
    )
    from office_connect.modules.reimbursement.models import ReimbAttachment
    from office_connect.modules.reimbursement.services import attachments as evidence

    for join in (
        (
            await app_session.execute(
                select(ReimbAttachment).where(
                    ReimbAttachment.claim_id == cast.claim.id
                )
            )
        )
        .scalars()
        .all()
    ):
        await evidence.remove_claim_evidence(
            app_session, join=join, actor_user_id=cast.owner.id
        )

    claim = await claim_action(
        app_session,
        claim_id=cast.claim.id,
        action="return",
        actor_user_id=cast.approver.id,
        comment="Your travel order is missing.",
        reason_ids=await return_reason_ids(app_session),
    )
    assert claim.status == "returned"


async def test_submit_stays_on_offer_even_with_an_incomplete_packet(
    make_user, seed_rbac, app_session, reimb_flag_on
):
    """Spec §9.3 step 5 renders the button plus the blocking list inline, so
    withholding the verb would make the goal invisible. Contrast `approve`,
    where the button is withheld and a callout explains."""
    cast = await standard_cast(app_session, make_user, packet=False)
    verbs = await claim_actions(
        app_session, claim=cast.claim, actor_user_id=cast.owner.id
    )
    assert verbs == ["submit", "cancel"]
