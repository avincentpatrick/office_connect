"""Per-instance step rows: activation (with SLA stamping) + fan-in evaluation.

Entering an approval-gate state spawns ``step.count`` step rows pinned with the
state's permission + the instance's org unit (so later config edits never reroute a
live item). Fan-in is decided by counting completed step rows in one locked
transaction — sequential (one step, join 'all') and parallel/four-eyes (N steps, join
'all'/'quorum') share this exact shape.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.models import WorkflowInstance, WorkflowState, WorkflowStep
from office_connect.core.time import ensure_aware


async def activate_state_steps(
    session: AsyncSession,
    *,
    instance: WorkflowInstance,
    state: WorkflowState,
    now: datetime,
) -> list[WorkflowStep]:
    """Create the active step rows for an approval-gate state. No-op (returns []) for
    a non-gate state. ``sla_due_at`` is stamped from the state's ``sla_hours``."""
    if not state.is_approval_gate:
        return []
    due = (
        ensure_aware(now) + timedelta(hours=state.sla_hours)
        if state.sla_hours
        else None
    )
    steps: list[WorkflowStep] = []
    for seq in range(max(1, state.step_count)):
        step = WorkflowStep(
            instance_id=instance.id,
            state_id=state.id,
            revision_no=instance.revision_no,
            sequence_no=seq,
            join_type=state.join_type,
            quorum_count=state.quorum_count,
            required_permission=state.required_permission,
            org_unit_id=instance.org_unit_id,
            status="active",
            sla_due_at=due,
        )
        session.add(step)
        steps.append(step)
    await session.flush()
    return steps


async def gate_steps(
    session: AsyncSession,
    *,
    instance_id: int,
    state_id: int,
    revision_no: int | None = None,
    lock: bool = False,
) -> list[WorkflowStep]:
    """Step rows for an instance's gate state. Pass ``revision_no`` to scope to the
    current activation (fan-in); locked for the transition transaction when asked."""
    stmt = select(WorkflowStep).where(
        WorkflowStep.instance_id == instance_id,
        WorkflowStep.state_id == state_id,
    )
    if revision_no is not None:
        stmt = stmt.where(WorkflowStep.revision_no == revision_no)
    if lock:
        stmt = stmt.with_for_update()
    return list((await session.execute(stmt)).scalars())


def join_satisfied(steps: list[WorkflowStep]) -> bool:
    """True when the gate's fan-in condition is met, per the steps' shared join type.
    Counts only LIVE steps (active/done) — returned/skipped rows never block a gate."""
    live = [s for s in steps if s.status in ("active", "done")]
    if not live:
        return False
    done = sum(1 for s in live if s.status == "done")
    total = len(live)
    join_type = live[0].join_type
    if join_type == "any":
        return done >= 1
    if join_type == "quorum":
        return done >= (live[0].quorum_count or total)
    return done >= total  # 'all'
