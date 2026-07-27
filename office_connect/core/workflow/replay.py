"""Event-sourcing consistency: fold the append-only log, prove the read-model.

``core_workflow_instances.current_state_id`` is a denormalized read-model kept only
for query speed. The authoritative history is ``core_workflow_events``. Folding the
events (each ``started``/``transition`` sets the state to its ``to_state_id``) MUST
reproduce the stored ``current_state_id`` — a cheap, continuous proof (a natural
companion to the audit hash-chain verification) that nothing wrote state out of band.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.models import WorkflowEvent, WorkflowInstance


def fold_events(events: Sequence[WorkflowEvent]) -> int | None:
    """Reduce events (ascending id) to the derived current state id. Escalation /
    reminder / note events carry no ``to_state_id`` and are skipped."""
    state_id: int | None = None
    for event in events:
        if event.event_type in ("started", "transition") and event.to_state_id is not None:
            state_id = event.to_state_id
    return state_id


async def folded_state_id(session: AsyncSession, instance_id: int) -> int | None:
    events = list(
        (
            await session.execute(
                select(WorkflowEvent)
                .where(WorkflowEvent.instance_id == instance_id)
                .order_by(WorkflowEvent.id)
            )
        ).scalars()
    )
    return fold_events(events)


async def is_consistent(session: AsyncSession, instance_id: int) -> bool:
    """True iff the folded event state equals the stored ``current_state_id``."""
    instance = await session.get(WorkflowInstance, instance_id)
    if instance is None:
        return False
    return await folded_state_id(session, instance_id) == instance.current_state_id
