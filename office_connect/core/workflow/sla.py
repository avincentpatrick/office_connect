"""SLA sweep — idempotent, non-interrupting escalation of overdue steps.

A step gets an ``sla_due_at`` at activation. This pure sweep finds active, overdue,
not-yet-escalated steps and appends ONE ``escalation`` event per step, marking the
step's ``escalation_level``. It is:

- **non-interrupting** (BPMN sense): the step stays ``active`` and the instance does not
  move — escalation is a nudge, never an auto-reroute;
- **idempotent**: ``SELECT ... FOR UPDATE SKIP LOCKED`` keeps concurrent sweeps off the
  same rows, and the partial-unique ``(step_id, escalation_level)`` index is the
  at-least-once backstop against a double-fire.

First cut escalates a step once (``escalation_level`` 0 → 1); the recurring reminder
ladder + notification delivery are deferred to R-4-app (which registers a notifier via
``register_sla_enqueuer``). Keeping core worker-free, the Celery beat task in
``ops/workflow_tasks.py`` calls this in an app session.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.models import WorkflowEvent, WorkflowStep
from office_connect.core.time import utc_now

# Optional ops→core injection: called with each escalated step id after flush so ops
# can enqueue a notification. Unregistered this session (delivery deferred to R-4-app).
_enqueuer: Callable[[int], None] | None = None


def register_sla_enqueuer(fn: Callable[[int], None] | None) -> None:
    """Install (or clear) the escalation-notification hook (ops → core injection)."""
    global _enqueuer
    _enqueuer = fn


async def sweep_due_steps(
    session: AsyncSession, *, now: datetime | None = None, limit: int = 200
) -> dict[str, Any]:
    """Escalate overdue active steps once. Returns ``{"due", "escalated"}``."""
    now = now or utc_now()
    steps = list(
        (
            await session.execute(
                select(WorkflowStep)
                .where(
                    WorkflowStep.status == "active",
                    WorkflowStep.escalation_level == 0,
                    WorkflowStep.sla_due_at.is_not(None),
                    WorkflowStep.sla_due_at <= now,
                )
                .order_by(WorkflowStep.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        ).scalars()
    )
    for step in steps:
        level = step.escalation_level + 1
        session.add(
            WorkflowEvent(
                instance_id=step.instance_id,
                step_id=step.id,
                event_type="escalation",
                escalation_level=level,
            )
        )
        step.escalation_level = level
    await session.flush()

    if _enqueuer is not None:
        for step in steps:
            _enqueuer(step.id)

    return {"due": len(steps), "escalated": len(steps)}
