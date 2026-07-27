"""Concurrency: two approvers acting at once — exactly one wins, one gets a 409.

The instance ``SELECT ... FOR UPDATE`` serializes the two transactions; the loser,
finding the item already in a terminal state, gets a structured conflict (not a silent
double-approval). Uses two independent sessions on real connections.
"""

import asyncio

from sqlalchemy import select

from office_connect.core import workflow as wf
from office_connect.core.api.errors import APIError
from office_connect.core.db import SessionLocal
from office_connect.core.models import WorkflowEvent, WorkflowInstance
from tests.workflow_helpers import build_chain


async def _try_approve(instance_id: int, actor_id: int) -> str:
    async with SessionLocal() as session:
        try:
            await wf.execute_action(
                session, instance_id=instance_id, action="approve", actor_user_id=actor_id
            )
            await session.commit()
            return "ok"
        except APIError as exc:
            await session.rollback()
            return exc.code


async def test_concurrent_approve_exactly_one_wins(app_session, seed_rbac, make_user):
    staff, _ = await make_user(roles=("staff",))
    a, _ = await make_user(roles=("approver",))
    b, _ = await make_user(roles=("approver",))
    chain = await build_chain(app_session)

    inst = await wf.start_instance(app_session, definition_code=chain.definition.code, actor_user_id=staff.id)
    await wf.execute_action(app_session, instance_id=inst.id, action="submit", actor_user_id=staff.id)
    instance_id = inst.id
    approved_state_id = chain.states["approved"].id
    await app_session.commit()

    results = await asyncio.gather(
        _try_approve(instance_id, a.id), _try_approve(instance_id, b.id)
    )

    assert results.count("ok") == 1, results
    loser = [r for r in results if r != "ok"]
    assert len(loser) == 1
    assert loser[0] in ("workflow_state_conflict", "workflow_step_already_acted"), loser

    # Exactly one approve transition landed, and the item is approved once.
    async with SessionLocal() as check:
        final = await check.get(WorkflowInstance, instance_id)
        assert final.current_state_id == approved_state_id
        approvals = list(
            (
                await check.execute(
                    select(WorkflowEvent).where(
                        WorkflowEvent.instance_id == instance_id,
                        WorkflowEvent.action == "approve",
                    )
                )
            ).scalars()
        )
        assert len(approvals) == 1
