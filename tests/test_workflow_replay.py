"""Event-sourcing consistency: folding the append-only log reproduces the read-model."""

from office_connect.core import workflow as wf
from tests.workflow_helpers import build_chain


async def test_fold_equals_stored_state(app_session, seed_rbac, make_user):
    staff, _ = await make_user(roles=("staff",))
    approver, _ = await make_user(roles=("approver",))
    chain = await build_chain(app_session)

    inst = await wf.start_instance(app_session, definition_code=chain.definition.code, actor_user_id=staff.id)
    await wf.execute_action(app_session, instance_id=inst.id, action="submit", actor_user_id=staff.id)
    await wf.execute_action(
        app_session, instance_id=inst.id, action="return",
        actor_user_id=approver.id, comment="Redo.",
    )
    await wf.execute_action(app_session, instance_id=inst.id, action="resubmit", actor_user_id=staff.id)
    await wf.execute_action(app_session, instance_id=inst.id, action="approve", actor_user_id=approver.id)

    folded = await wf.folded_state_id(app_session, inst.id)
    assert folded == inst.current_state_id == chain.states["approved"].id
    assert await wf.is_consistent(app_session, inst.id) is True


async def test_partial_approval_folds_to_same_state(app_session, seed_rbac, make_user):
    """A partial (four-eyes) approval records a transition to the SAME state — the
    fold must still equal the stored state (no spurious move)."""
    staff, _ = await make_user(roles=("staff",))
    a, _ = await make_user(roles=("approver",))
    chain = await build_chain(app_session, step_count=2, join_type="all")

    inst = await wf.start_instance(app_session, definition_code=chain.definition.code, actor_user_id=staff.id)
    await wf.execute_action(app_session, instance_id=inst.id, action="submit", actor_user_id=staff.id)
    await wf.execute_action(app_session, instance_id=inst.id, action="approve", actor_user_id=a.id)

    assert inst.current_state_id == chain.states["for_approval"].id
    assert await wf.folded_state_id(app_session, inst.id) == chain.states["for_approval"].id
    assert await wf.is_consistent(app_session, inst.id) is True
