"""SLA sweep: stamps deadlines, escalates once, non-interrupting, no double-fire."""

from datetime import timedelta

from sqlalchemy import select

from office_connect.core import workflow as wf
from office_connect.core.models import WorkflowEvent, WorkflowStep
from office_connect.core.time import utc_now
from tests.workflow_helpers import build_chain


async def _escalations(session, instance_id):
    return list(
        (
            await session.execute(
                select(WorkflowEvent).where(
                    WorkflowEvent.instance_id == instance_id,
                    WorkflowEvent.event_type == "escalation",
                )
            )
        ).scalars()
    )


async def test_overdue_step_escalates_once_and_is_non_interrupting(
    app_session, seed_rbac, make_user
):
    staff, _ = await make_user(roles=("staff",))
    chain = await build_chain(app_session, sla_hours=72)

    t0 = utc_now()
    inst = await wf.start_instance(app_session, definition_code=chain.definition.code, actor_user_id=staff.id)
    # Submit "in the past" so the gate step's sla_due_at (t0 + 72h) is overdue.
    await wf.execute_action(
        app_session, instance_id=inst.id, action="submit",
        actor_user_id=staff.id, now=t0,
    )

    later = t0 + timedelta(hours=100)
    result = await wf.sweep_due_steps(app_session, now=later)
    assert result["escalated"] == 1

    events = await _escalations(app_session, inst.id)
    assert len(events) == 1
    assert events[0].escalation_level == 1

    # Non-interrupting: the step is still active and the instance did not move.
    step = (
        await app_session.execute(
            select(WorkflowStep).where(WorkflowStep.instance_id == inst.id)
        )
    ).scalars().one()
    assert step.status == "active"
    assert inst.current_state_id == chain.states["for_approval"].id

    # No double-fire: a second sweep at the same time escalates nothing more.
    again = await wf.sweep_due_steps(app_session, now=later)
    assert again["escalated"] == 0
    assert len(await _escalations(app_session, inst.id)) == 1


async def test_not_yet_due_is_not_swept(app_session, seed_rbac, make_user):
    staff, _ = await make_user(roles=("staff",))
    chain = await build_chain(app_session, sla_hours=72)
    t0 = utc_now()
    inst = await wf.start_instance(app_session, definition_code=chain.definition.code, actor_user_id=staff.id)
    await wf.execute_action(app_session, instance_id=inst.id, action="submit", actor_user_id=staff.id, now=t0)

    # Only 1 hour later — well within the 72h deadline.
    result = await wf.sweep_due_steps(app_session, now=t0 + timedelta(hours=1))
    assert result["escalated"] == 0
    assert len(await _escalations(app_session, inst.id)) == 0
