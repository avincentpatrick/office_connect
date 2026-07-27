"""Design-time: graph validation, one-way publish (immutability), version pinning."""

import pytest

from office_connect.core import workflow as wf
from office_connect.core.api.errors import APIError


async def test_graph_requires_single_initial_and_terminal(app_session):
    defn = await wf.create_definition(app_session, code="g.no-initial", name="x")
    v = await wf.create_version(app_session, definition=defn)
    a = await wf.add_state(app_session, version=v, code="a", name="a", kind="normal")
    b = await wf.add_state(app_session, version=v, code="b", name="b", kind="terminal")
    await wf.add_transition(app_session, version=v, from_state=a, to_state=b, action="submit")
    with pytest.raises(APIError) as ei:
        await wf.publish_version(app_session, version=v)
    assert ei.value.code == "workflow_invalid_definition"


async def test_graph_rejects_dead_end_nonterminal(app_session):
    defn = await wf.create_definition(app_session, code="g.deadend", name="x")
    v = await wf.create_version(app_session, definition=defn)
    await wf.add_state(app_session, version=v, code="draft", name="d", kind="initial")
    # A non-terminal state with no outgoing transition is invalid.
    await wf.add_state(app_session, version=v, code="stuck", name="s", kind="normal")
    await wf.add_state(app_session, version=v, code="done", name="done", kind="terminal")
    draft = (await _states(app_session, v.id))["draft"]
    stuck = (await _states(app_session, v.id))["stuck"]
    await wf.add_transition(app_session, version=v, from_state=draft, to_state=stuck, action="submit")
    with pytest.raises(APIError) as ei:
        await wf.publish_version(app_session, version=v)
    assert ei.value.code == "workflow_invalid_definition"


async def test_publish_is_one_way_and_freezes(app_session):
    defn = await wf.create_definition(app_session, code="g.freeze", name="x")
    v = await wf.create_version(app_session, definition=defn)
    draft = await wf.add_state(app_session, version=v, code="draft", name="d", kind="initial")
    done = await wf.add_state(app_session, version=v, code="done", name="done", kind="terminal")
    await wf.add_transition(app_session, version=v, from_state=draft, to_state=done, action="submit")
    await wf.publish_version(app_session, version=v)

    with pytest.raises(APIError) as ei:
        await wf.add_state(app_session, version=v, code="late", name="late", kind="normal")
    assert ei.value.code == "workflow_version_published"


async def test_version_pinning(app_session, seed_rbac, make_user):
    """An in-flight instance stays on its version even after a newer one publishes."""
    staff, _ = await make_user(roles=("staff",))
    defn = await wf.create_definition(app_session, code="g.pin", name="x")

    v1 = await wf.create_version(app_session, definition=defn)
    d1 = await wf.add_state(app_session, version=v1, code="draft", name="d", kind="initial")
    done1 = await wf.add_state(app_session, version=v1, code="done", name="done", kind="terminal")
    await wf.add_transition(app_session, version=v1, from_state=d1, to_state=done1, action="submit")
    await wf.publish_version(app_session, version=v1)

    inst = await wf.start_instance(app_session, definition_code=defn.code, actor_user_id=staff.id)
    assert inst.definition_version_id == v1.id

    # Publish v2 with a different graph.
    v2 = await wf.create_version(app_session, definition=defn)
    d2 = await wf.add_state(app_session, version=v2, code="draft", name="d", kind="initial")
    done2 = await wf.add_state(app_session, version=v2, code="done", name="done", kind="terminal")
    await wf.add_transition(app_session, version=v2, from_state=d2, to_state=done2, action="submit")
    await wf.publish_version(app_session, version=v2)

    # The in-flight instance is still pinned to v1; a NEW instance uses v2.
    assert inst.definition_version_id == v1.id
    fresh = await wf.start_instance(app_session, definition_code=defn.code, actor_user_id=staff.id)
    assert fresh.definition_version_id == v2.id


async def _states(session, version_id):
    from sqlalchemy import select

    from office_connect.core.models import WorkflowState

    rows = (
        await session.execute(
            select(WorkflowState).where(WorkflowState.definition_version_id == version_id)
        )
    ).scalars()
    return {s.code: s for s in rows}
