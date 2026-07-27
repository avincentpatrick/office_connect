"""Org-scoped approval routing: a scoped grant covers its unit + subtree, no wider."""

import pytest

from office_connect.core import workflow as wf
from office_connect.core.api.errors import APIError
from tests.workflow_helpers import build_chain, grant_scoped_role, make_org_unit


async def _to_gate(session, chain, originator):
    inst = await wf.start_instance(
        session,
        definition_code=chain.definition.code,
        actor_user_id=originator.id,
        org_unit_id=chain._org_a_id,
    )
    await wf.execute_action(session, instance_id=inst.id, action="submit", actor_user_id=originator.id)
    return inst


async def test_scoped_approver_within_subtree_may_act(app_session, seed_rbac, make_user):
    office = await make_org_unit(app_session, kind="office")
    div_a = await make_org_unit(app_session, kind="division", parent=office)
    div_b = await make_org_unit(app_session, kind="division", parent=office)

    staff, _ = await make_user(roles=("staff",))
    in_a, _ = await make_user(roles=())
    in_b, _ = await make_user(roles=())
    at_office, _ = await make_user(roles=())
    await grant_scoped_role(app_session, user=in_a, role_code="approver", org_unit_id=div_a.id)
    await grant_scoped_role(app_session, user=in_b, role_code="approver", org_unit_id=div_b.id)
    await grant_scoped_role(app_session, user=at_office, role_code="approver", org_unit_id=office.id)

    chain = await build_chain(app_session)
    chain._org_a_id = div_a.id

    # An approver scoped to a sibling division cannot act.
    inst = await _to_gate(app_session, chain, staff)
    with pytest.raises(APIError) as ei:
        await wf.execute_action(app_session, instance_id=inst.id, action="approve", actor_user_id=in_b.id)
    assert ei.value.status_code == 403
    assert ei.value.code == "workflow_not_authorized"

    # An ancestor-scoped approver (office) covers the division subtree.
    await wf.execute_action(app_session, instance_id=inst.id, action="approve", actor_user_id=at_office.id)
    assert inst.current_state_id == chain.states["approved"].id


async def test_scoped_approver_in_unit_may_act(app_session, seed_rbac, make_user):
    office = await make_org_unit(app_session, kind="office")
    div_a = await make_org_unit(app_session, kind="division", parent=office)

    staff, _ = await make_user(roles=("staff",))
    in_a, _ = await make_user(roles=())
    await grant_scoped_role(app_session, user=in_a, role_code="approver", org_unit_id=div_a.id)

    chain = await build_chain(app_session)
    chain._org_a_id = div_a.id
    inst = await _to_gate(app_session, chain, staff)

    await wf.execute_action(app_session, instance_id=inst.id, action="approve", actor_user_id=in_a.id)
    assert inst.current_state_id == chain.states["approved"].id
