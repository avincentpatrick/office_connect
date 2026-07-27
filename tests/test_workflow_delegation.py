"""Delegation / OIC: a delegate may act, recorded as on-behalf-of the delegator."""

from datetime import timedelta

import pytest

from office_connect.core import workflow as wf
from office_connect.core.api.errors import APIError
from office_connect.core.models import WorkflowDelegation
from office_connect.core.time import utc_now
from tests.workflow_helpers import build_chain, grant_scoped_role, make_org_unit


async def _setup(app_session, make_user):
    office = await make_org_unit(app_session, kind="office")
    div = await make_org_unit(app_session, kind="division", parent=office)
    staff, _ = await make_user(roles=("staff",))
    reyes, _ = await make_user(roles=())  # the real approver
    cruz, _ = await make_user(roles=())   # the OIC, no approve grant of their own
    await grant_scoped_role(app_session, user=reyes, role_code="approver", org_unit_id=div.id)
    chain = await build_chain(app_session)
    inst = await wf.start_instance(
        app_session, definition_code=chain.definition.code,
        actor_user_id=staff.id, org_unit_id=div.id,
    )
    await wf.execute_action(app_session, instance_id=inst.id, action="submit", actor_user_id=staff.id)
    return chain, inst, reyes, cruz, div


async def test_delegate_may_act_on_behalf_of(app_session, seed_rbac, make_user):
    chain, inst, reyes, cruz, div = await _setup(app_session, make_user)

    now = utc_now()
    app_session.add(
        WorkflowDelegation(
            delegator_user_id=reyes.id,
            delegate_user_id=cruz.id,
            org_unit_id=div.id,
            starts_at=now - timedelta(days=1),
            ends_at=now + timedelta(days=1),
            reason="Reyes on leave; Cruz is OIC.",
        )
    )
    await app_session.flush()

    event = await wf.execute_action(
        app_session, instance_id=inst.id, action="approve", actor_user_id=cruz.id
    )
    assert inst.current_state_id == chain.states["approved"].id
    assert event.actor_user_id == cruz.id
    assert event.on_behalf_of_user_id == reyes.id


async def test_without_delegation_is_forbidden(app_session, seed_rbac, make_user):
    chain, inst, reyes, cruz, div = await _setup(app_session, make_user)
    # Cruz holds no approve grant and no delegation → 403.
    with pytest.raises(APIError) as ei:
        await wf.execute_action(app_session, instance_id=inst.id, action="approve", actor_user_id=cruz.id)
    assert ei.value.status_code == 403


async def test_expired_delegation_does_not_authorize(app_session, seed_rbac, make_user):
    chain, inst, reyes, cruz, div = await _setup(app_session, make_user)
    now = utc_now()
    app_session.add(
        WorkflowDelegation(
            delegator_user_id=reyes.id,
            delegate_user_id=cruz.id,
            org_unit_id=div.id,
            starts_at=now - timedelta(days=5),
            ends_at=now - timedelta(days=1),  # already ended
            reason="stale",
        )
    )
    await app_session.flush()
    with pytest.raises(APIError) as ei:
        await wf.execute_action(app_session, instance_id=inst.id, action="approve", actor_user_id=cruz.id)
    assert ei.value.status_code == 403
