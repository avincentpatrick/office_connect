"""Segregation of duties at an approval gate — no self-approval; distinct approvers."""

import pytest

from office_connect.core import workflow as wf
from office_connect.core.api.errors import APIError
from tests.workflow_helpers import build_chain


async def test_self_approval_blocked(app_session, seed_rbac, make_user):
    # The originator holds BOTH submit and approve, so authorization passes and the
    # segregation check is what must stop them approving their own claim.
    owner, _ = await make_user(roles=("staff", "approver"))
    chain = await build_chain(app_session, enforce_segregation=True)

    inst = await wf.start_instance(app_session, definition_code=chain.definition.code, actor_user_id=owner.id)
    await wf.execute_action(app_session, instance_id=inst.id, action="submit", actor_user_id=owner.id)

    with pytest.raises(APIError) as ei:
        await wf.execute_action(
            app_session, instance_id=inst.id, action="approve", actor_user_id=owner.id
        )
    assert ei.value.status_code == 409
    assert ei.value.code == "segregation_of_duties"


async def test_distinct_approver_passes(app_session, seed_rbac, make_user):
    owner, _ = await make_user(roles=("staff",))
    approver, _ = await make_user(roles=("approver",))
    chain = await build_chain(app_session, enforce_segregation=True)

    inst = await wf.start_instance(app_session, definition_code=chain.definition.code, actor_user_id=owner.id)
    await wf.execute_action(app_session, instance_id=inst.id, action="submit", actor_user_id=owner.id)
    await wf.execute_action(app_session, instance_id=inst.id, action="approve", actor_user_id=approver.id)
    assert inst.current_state_id == chain.states["approved"].id


async def test_four_eyes_needs_two_distinct(app_session, seed_rbac, make_user):
    """A parallel gate (step_count=2, join 'all') needs two DISTINCT approvers."""
    owner, _ = await make_user(roles=("staff",))
    a, _ = await make_user(roles=("approver",))
    b, _ = await make_user(roles=("approver",))
    chain = await build_chain(
        app_session, enforce_segregation=True, step_count=2, join_type="all"
    )

    inst = await wf.start_instance(app_session, definition_code=chain.definition.code, actor_user_id=owner.id)
    await wf.execute_action(app_session, instance_id=inst.id, action="submit", actor_user_id=owner.id)

    # First approver fills one slot; the gate is not yet satisfied.
    await wf.execute_action(app_session, instance_id=inst.id, action="approve", actor_user_id=a.id)
    assert inst.current_state_id == chain.states["for_approval"].id

    # The same person cannot fill the second slot.
    with pytest.raises(APIError) as ei:
        await wf.execute_action(app_session, instance_id=inst.id, action="approve", actor_user_id=a.id)
    assert ei.value.code == "workflow_step_already_acted"

    # A distinct approver completes the four-eyes gate.
    await wf.execute_action(app_session, instance_id=inst.id, action="approve", actor_user_id=b.id)
    assert inst.current_state_id == chain.states["approved"].id


# --- R-4-screens: the guards must also be reflected in available_actions ----


async def test_available_actions_withholds_approve_from_the_originator(
    app_session, seed_rbac, make_user
):
    """workflow-standards §3: an action this endpoint lists is one
    ``execute_action`` would accept NOW. Before R-4-screens the originator was
    offered Approve and the POST 409'd — the UI has no way to know better,
    because it is forbidden from computing permissions itself."""
    owner, _ = await make_user(roles=("staff", "approver"))
    checker, _ = await make_user(roles=("approver",))
    chain = await build_chain(app_session, enforce_segregation=True)

    inst = await wf.start_instance(
        app_session, definition_code=chain.definition.code, actor_user_id=owner.id
    )
    await wf.execute_action(
        app_session, instance_id=inst.id, action="submit", actor_user_id=owner.id
    )

    mine = await wf.available_actions(
        app_session, instance_id=inst.id, actor_user_id=owner.id
    )
    assert "approve" not in mine
    assert "return" in mine  # returning your own claim is not self-approval

    theirs = await wf.available_actions(
        app_session, instance_id=inst.id, actor_user_id=checker.id
    )
    assert "approve" in theirs


async def test_available_actions_withholds_approve_from_a_filled_slot(
    app_session, seed_rbac, make_user
):
    """The distinct-approver rule, same doctrine: after filling one slot of a
    four-eyes gate, Approve is no longer on offer for that actor."""
    owner, _ = await make_user(roles=("staff",))
    a, _ = await make_user(roles=("approver",))
    b, _ = await make_user(roles=("approver",))
    chain = await build_chain(
        app_session, enforce_segregation=True, step_count=2, join_type="all"
    )

    inst = await wf.start_instance(
        app_session, definition_code=chain.definition.code, actor_user_id=owner.id
    )
    await wf.execute_action(
        app_session, instance_id=inst.id, action="submit", actor_user_id=owner.id
    )
    await wf.execute_action(
        app_session, instance_id=inst.id, action="approve", actor_user_id=a.id
    )

    assert "approve" not in await wf.available_actions(
        app_session, instance_id=inst.id, actor_user_id=a.id
    )
    assert "approve" in await wf.available_actions(
        app_session, instance_id=inst.id, actor_user_id=b.id
    )
