"""The transition executor: happy path, guard routing, comments, terminal, CAS,
idempotency — the heart of the shared workflow engine (Stage C)."""

from decimal import Decimal

import pytest

from office_connect.core import workflow as wf
from office_connect.core.api.errors import APIError
from tests.workflow_helpers import build_chain

# ``execute_action`` loads the instance via the identity map, so the object
# ``start_instance`` returned reflects each mutation in place — assert on it directly
# (expire_all() would trigger an async-unsafe lazy load; refresh() is the safe reload).


async def test_happy_path_submit_then_approve(app_session, seed_rbac, make_user):
    staff, _ = await make_user(roles=("staff",))
    approver, _ = await make_user(roles=("approver",))
    chain = await build_chain(app_session)

    inst = await wf.start_instance(
        app_session, definition_code=chain.definition.code, actor_user_id=staff.id
    )
    assert inst.current_state_id == chain.states["draft"].id

    await wf.execute_action(
        app_session, instance_id=inst.id, action="submit", actor_user_id=staff.id
    )
    assert inst.current_state_id == chain.states["for_approval"].id

    await wf.execute_action(
        app_session, instance_id=inst.id, action="approve", actor_user_id=approver.id
    )
    assert inst.current_state_id == chain.states["approved"].id


async def test_amount_guard_routes(app_session, seed_rbac, make_user):
    staff, _ = await make_user(roles=("staff",))
    approver, _ = await make_user(roles=("approver",))
    chain = await build_chain(app_session, amount_split=True)

    # Small claim: approve → approved directly.
    small = await wf.start_instance(
        app_session, definition_code=chain.definition.code,
        actor_user_id=staff.id, amount=Decimal("500.00"),
    )
    await wf.execute_action(app_session, instance_id=small.id, action="submit", actor_user_id=staff.id)
    await wf.execute_action(app_session, instance_id=small.id, action="approve", actor_user_id=approver.id)
    assert small.current_state_id == chain.states["approved"].id

    # Large claim: approve routes to for_director, then approve → approved.
    big = await wf.start_instance(
        app_session, definition_code=chain.definition.code,
        actor_user_id=staff.id, amount=Decimal("2000.00"),
    )
    await wf.execute_action(app_session, instance_id=big.id, action="submit", actor_user_id=staff.id)
    await wf.execute_action(app_session, instance_id=big.id, action="approve", actor_user_id=approver.id)
    assert big.current_state_id == chain.states["for_director"].id
    await wf.execute_action(app_session, instance_id=big.id, action="approve", actor_user_id=approver.id)
    assert big.current_state_id == chain.states["approved"].id


async def test_return_requires_comment(app_session, seed_rbac, make_user):
    staff, _ = await make_user(roles=("staff",))
    approver, _ = await make_user(roles=("approver",))
    chain = await build_chain(app_session)
    inst = await wf.start_instance(app_session, definition_code=chain.definition.code, actor_user_id=staff.id)
    await wf.execute_action(app_session, instance_id=inst.id, action="submit", actor_user_id=staff.id)

    with pytest.raises(APIError) as ei:
        await wf.execute_action(
            app_session, instance_id=inst.id, action="return", actor_user_id=approver.id
        )
    assert ei.value.status_code == 422
    assert ei.value.code == "workflow_comment_required"

    await wf.execute_action(
        app_session, instance_id=inst.id, action="return",
        actor_user_id=approver.id, comment="Missing the taxi receipt.",
    )
    assert inst.current_state_id == chain.states["returned"].id


async def test_terminal_state_conflict(app_session, seed_rbac, make_user):
    staff, _ = await make_user(roles=("staff",))
    approver, _ = await make_user(roles=("approver",))
    chain = await build_chain(app_session)
    inst = await wf.start_instance(app_session, definition_code=chain.definition.code, actor_user_id=staff.id)
    await wf.execute_action(app_session, instance_id=inst.id, action="submit", actor_user_id=staff.id)
    await wf.execute_action(app_session, instance_id=inst.id, action="approve", actor_user_id=approver.id)

    with pytest.raises(APIError) as ei:
        await wf.execute_action(
            app_session, instance_id=inst.id, action="approve", actor_user_id=approver.id
        )
    assert ei.value.status_code == 409
    assert ei.value.code == "workflow_state_conflict"


async def test_transition_not_allowed(app_session, seed_rbac, make_user):
    staff, _ = await make_user(roles=("staff",))
    approver, _ = await make_user(roles=("approver",))
    chain = await build_chain(app_session)
    inst = await wf.start_instance(app_session, definition_code=chain.definition.code, actor_user_id=staff.id)
    # 'approve' is not legal from Draft.
    with pytest.raises(APIError) as ei:
        await wf.execute_action(
            app_session, instance_id=inst.id, action="approve", actor_user_id=approver.id
        )
    assert ei.value.status_code == 422
    assert ei.value.code == "workflow_transition_not_allowed"


async def test_idempotency_replay(app_session, seed_rbac, make_user):
    staff, _ = await make_user(roles=("staff",))
    approver, _ = await make_user(roles=("approver",))
    chain = await build_chain(app_session)
    inst = await wf.start_instance(app_session, definition_code=chain.definition.code, actor_user_id=staff.id)
    await wf.execute_action(app_session, instance_id=inst.id, action="submit", actor_user_id=staff.id)

    first = await wf.execute_action(
        app_session, instance_id=inst.id, action="approve",
        actor_user_id=approver.id, idempotency_key="dup-1",
    )
    replay = await wf.execute_action(
        app_session, instance_id=inst.id, action="approve",
        actor_user_id=approver.id, idempotency_key="dup-1",
    )
    assert replay.id == first.id  # same event, no second action
    assert inst.current_state_id == chain.states["approved"].id


async def test_cas_stale_version(app_session, seed_rbac, make_user):
    staff, _ = await make_user(roles=("staff",))
    approver, _ = await make_user(roles=("approver",))
    chain = await build_chain(app_session)
    inst = await wf.start_instance(app_session, definition_code=chain.definition.code, actor_user_id=staff.id)
    await wf.execute_action(app_session, instance_id=inst.id, action="submit", actor_user_id=staff.id)

    with pytest.raises(APIError) as ei:
        await wf.execute_action(
            app_session, instance_id=inst.id, action="approve",
            actor_user_id=approver.id, expected_version=999,
        )
    assert ei.value.status_code == 409
    assert ei.value.code == "stale_workflow_version"

    # The correct version still works.
    await wf.execute_action(
        app_session, instance_id=inst.id, action="approve",
        actor_user_id=approver.id, expected_version=inst.row_version,
    )
    assert inst.current_state_id == chain.states["approved"].id
