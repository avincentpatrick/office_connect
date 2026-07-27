"""Feature-flag semantics: OFF blocks NEW instances only; in-flight always finishes."""

import secrets

import pytest

from office_connect.core import workflow as wf
from office_connect.core.api.errors import APIError
from office_connect.core.models import FeatureFlag
from tests.workflow_helpers import build_chain


async def _flag(app_session, key, *, enabled):
    flag = FeatureFlag(key=key, enabled=enabled, is_active=True)
    app_session.add(flag)
    await app_session.flush()
    return flag


async def test_flag_off_blocks_new_instance(app_session, seed_rbac, make_user):
    staff, _ = await make_user(roles=("staff",))
    key = f"module.test.{secrets.token_hex(4)}"
    chain = await build_chain(app_session, module=key)
    await _flag(app_session, key, enabled=False)

    with pytest.raises(APIError) as ei:
        await wf.start_instance(
            app_session, definition_code=chain.definition.code,
            actor_user_id=staff.id, feature_flag_key=key,
        )
    assert ei.value.status_code == 409
    assert ei.value.code == "workflow_module_disabled"


async def test_flag_on_allows_new_instance(app_session, seed_rbac, make_user):
    staff, _ = await make_user(roles=("staff",))
    key = f"module.test.{secrets.token_hex(4)}"
    chain = await build_chain(app_session, module=key)
    await _flag(app_session, key, enabled=True)

    inst = await wf.start_instance(
        app_session, definition_code=chain.definition.code,
        actor_user_id=staff.id, feature_flag_key=key,
    )
    assert inst.current_state_id == chain.states["draft"].id


async def test_in_flight_finishes_after_flag_off(app_session, seed_rbac, make_user):
    staff, _ = await make_user(roles=("staff",))
    approver, _ = await make_user(roles=("approver",))
    key = f"module.test.{secrets.token_hex(4)}"
    chain = await build_chain(app_session, module=key)
    flag = await _flag(app_session, key, enabled=True)

    inst = await wf.start_instance(
        app_session, definition_code=chain.definition.code,
        actor_user_id=staff.id, feature_flag_key=key,
    )

    # Turn the module OFF mid-flight.
    flag.enabled = False
    await app_session.flush()

    # New instances are blocked...
    with pytest.raises(APIError):
        await wf.start_instance(
            app_session, definition_code=chain.definition.code,
            actor_user_id=staff.id, feature_flag_key=key,
        )

    # ...but the in-flight one runs to completion (execute_action never reads the flag).
    await wf.execute_action(app_session, instance_id=inst.id, action="submit", actor_user_id=staff.id)
    await wf.execute_action(app_session, instance_id=inst.id, action="approve", actor_user_id=approver.id)
    assert inst.current_state_id == chain.states["approved"].id
