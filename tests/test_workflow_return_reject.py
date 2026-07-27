"""Return-vs-Reject: return loops back (resubmit restarts, revision++), reject ends."""

import pytest

from office_connect.core import workflow as wf
from office_connect.core.api.errors import APIError
from tests.workflow_helpers import build_chain


async def test_return_then_resubmit_restarts_chain(app_session, seed_rbac, make_user):
    staff, _ = await make_user(roles=("staff",))
    approver, _ = await make_user(roles=("approver",))
    chain = await build_chain(app_session)

    inst = await wf.start_instance(app_session, definition_code=chain.definition.code, actor_user_id=staff.id)
    await wf.execute_action(app_session, instance_id=inst.id, action="submit", actor_user_id=staff.id)
    assert inst.revision_no == 1

    await wf.execute_action(
        app_session, instance_id=inst.id, action="return",
        actor_user_id=approver.id, comment="Fix the itinerary dates.",
    )
    assert inst.current_state_id == chain.states["returned"].id

    # Resubmit re-enters the chain at the approval gate and bumps the revision.
    await wf.execute_action(app_session, instance_id=inst.id, action="resubmit", actor_user_id=staff.id)
    assert inst.current_state_id == chain.states["for_approval"].id
    assert inst.revision_no == 2

    # A fresh approval now lands.
    await wf.execute_action(app_session, instance_id=inst.id, action="approve", actor_user_id=approver.id)
    assert inst.current_state_id == chain.states["approved"].id


async def test_reject_is_terminal(app_session, seed_rbac, make_user):
    staff, _ = await make_user(roles=("staff",))
    approver, _ = await make_user(roles=("approver",))
    chain = await build_chain(app_session)

    inst = await wf.start_instance(app_session, definition_code=chain.definition.code, actor_user_id=staff.id)
    await wf.execute_action(app_session, instance_id=inst.id, action="submit", actor_user_id=staff.id)
    await wf.execute_action(
        app_session, instance_id=inst.id, action="reject",
        actor_user_id=approver.id, comment="Ineligible travel.",
    )
    assert inst.current_state_id == chain.states["rejected"].id

    # No further action from a terminal state.
    with pytest.raises(APIError) as ei:
        await wf.execute_action(app_session, instance_id=inst.id, action="resubmit", actor_user_id=staff.id)
    assert ei.value.status_code == 409
