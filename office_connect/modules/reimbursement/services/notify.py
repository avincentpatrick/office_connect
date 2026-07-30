"""SLA escalation delivery + the repeating holder-only reminder ladder.

Pure async service (NO celery import — ops wraps these in tasks), completing
the engine's SLA story for reimbursement:

- The engine sweep (``ops.sweep_workflow_sla``) escalates an overdue step ONCE
  and calls the registered enqueuer with the step id — **inside its own
  transaction, before commit**. ``notify_escalation`` is therefore written
  defensively: it re-reads committed state in ITS OWN session/task and no-ops
  when the escalation isn't (yet, or ever) visible; the ladder sweep below is
  the backstop that catches a missed first nudge (its ``k=0`` key is the same
  dedup key the escalation path uses).
- Spec §7.4's ladder — one nudge at the SLA, then one every
  ``sla.reminder_repeat_days`` (2) WORKING days — cannot come from the engine
  (it escalates once by design), so ``sweep_sla_reminders`` runs as an ops
  beat task. Nudge index ``k`` = Manila working days overdue ÷ the repeat
  cadence; the outbox ``dedup_key`` (``reimb.claim.sla:<step>:<k>``) makes
  every path idempotent no matter how often the beat fires.

**Holder only, never superiors** (spec §7.4, non-negotiable): the recipient is
always ``claim.holder_id``; an ``external_fms`` holder is never nudged (spec
§7.5's >10-WD follow-up is the Admin queue filter, not a notification).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.models import (
    WorkflowEvent,
    WorkflowInstance,
    WorkflowStep,
)
from office_connect.core.models.notification import NotificationOutbox
from office_connect.core.notifications import Notification
from office_connect.core.notifications.outbox import (
    dispatch_on_commit,
    persist_notification,
)
from office_connect.core.time import to_manila, utc_now
from office_connect.core.workdays import load_nonworking_dates, working_days_between
from office_connect.modules.reimbursement.models import ReimbClaim
from office_connect.modules.reimbursement.services import status as st
from office_connect.modules.reimbursement.services.lifecycle import (
    config_working_days,
)
from office_connect.modules.reimbursement.workflow import SUBJECT_KIND

DEDUP_PREFIX = "reimb.claim.sla"
_REMINDER_KEY = "sla.reminder_repeat_days"
_REMINDER_DEFAULT = 2


def _dedup_key(step_id: int, k: int) -> str:
    return f"{DEDUP_PREFIX}:{step_id}:{k}"


async def _already_sent(session: AsyncSession, dedup_key: str) -> bool:
    return (
        await session.execute(
            select(NotificationOutbox.id).where(
                NotificationOutbox.dedup_key == dedup_key,
                NotificationOutbox.status != "dead",
            )
        )
    ).scalars().first() is not None


async def _send_nudge(
    session: AsyncSession, *, claim: ReimbClaim, step: WorkflowStep, k: int
) -> int | None:
    """Persist one holder-only in-app nudge (idempotent on the dedup key).
    Returns the outbox id when a NEW row was written, else None."""
    if claim.holder_kind != "user" or claim.holder_id is None:
        return None  # external_fms / terminal — never nudged
    key = _dedup_key(step.id, k)
    if await _already_sent(session, key):
        return None
    ref = claim.ref_no or f"claim #{claim.id}"
    label = st.STATUS_LABELS.get(claim.status or "", claim.status or "?")
    when = "is past its SLA" if k == 0 else f"is still waiting (reminder #{k})"
    notification_id = await persist_notification(
        session,
        Notification(
            channel="in_app",
            meta={
                "dedup_key": key,
                "recipient_user_id": claim.holder_id,
                "module": "reimbursement",
                "kind": "sla_nudge",
                "subject": f"Reimbursement {ref} is waiting on you",
                "body_text": (
                    f"{ref} ({label}) {when} — "
                    f"{claim.next_action or 'take the next action'}."
                ),
            },
        ),
    )
    dispatch_on_commit(session, notification_id)
    return notification_id


async def notify_escalation(session: AsyncSession, *, step_id: int) -> int | None:
    """Deliver the first SLA nudge for an escalated step (the
    ``register_sla_enqueuer`` target, via the ops task). Defensive by design —
    see the module docstring: no-ops unless the committed step is active,
    escalated, and belongs to a reimbursement claim."""
    step = await session.get(WorkflowStep, step_id)
    if step is None or step.status != "active" or (step.escalation_level or 0) < 1:
        return None
    instance = await session.get(WorkflowInstance, step.instance_id)
    if (
        instance is None
        or instance.subject_kind != SUBJECT_KIND
        or instance.subject_id is None
    ):
        return None  # the seam is engine-generic; other modules opt in later
    claim = await session.get(ReimbClaim, instance.subject_id)
    if claim is None:
        return None
    return await _send_nudge(session, claim=claim, step=step, k=0)


async def sweep_sla_reminders(
    session: AsyncSession, *, now: datetime | None = None, limit: int = 200
) -> dict[str, int]:
    """The repeating ladder: for every escalated, still-active reimbursement
    step, send the k-th nudge once ``k * repeat`` working days have passed
    since the SLA fell due. Also the missed-first-nudge backstop (``k=0``).
    Flushes; the caller (ops task) commits."""
    now = now or utc_now()
    today = to_manila(now).date()

    steps = (
        (
            await session.execute(
                select(WorkflowStep)
                .join(
                    WorkflowInstance,
                    WorkflowInstance.id == WorkflowStep.instance_id,
                )
                .where(
                    WorkflowStep.status == "active",
                    WorkflowStep.escalation_level >= 1,
                    WorkflowStep.sla_due_at.is_not(None),
                    WorkflowStep.sla_due_at <= now,
                    WorkflowInstance.subject_kind == SUBJECT_KIND,
                )
                .order_by(WorkflowStep.id)
                .limit(limit)
                .with_for_update(skip_locked=True, of=WorkflowStep)
            )
        )
        .scalars()
        .all()
    )

    repeat = await config_working_days(
        session, key=_REMINDER_KEY, default=_REMINDER_DEFAULT, today=today
    )
    checked = nudged = 0
    for step in steps:
        checked += 1
        instance = await session.get(WorkflowInstance, step.instance_id)
        if instance.subject_id is None:
            continue
        claim = await session.get(ReimbClaim, instance.subject_id)
        if claim is None:
            continue
        due_local = to_manila(step.sla_due_at).date()
        nonworking = await load_nonworking_dates(
            session, min(due_local, today), today
        )
        overdue_wd = working_days_between(due_local, today, nonworking)
        if overdue_wd < 0:
            continue
        k = overdue_wd // repeat if repeat > 0 else 0
        notification_id = await _send_nudge(session, claim=claim, step=step, k=k)
        if notification_id is not None:
            nudged += 1
            if k > 0:
                # The decision-trail row for a repeat nudge (the escalation
                # partial-unique index constrains event_type='escalation' only;
                # dedup above guarantees one event per (step, k)).
                session.add(
                    WorkflowEvent(
                        instance_id=instance.id,
                        step_id=step.id,
                        event_type="reminder",
                        escalation_level=k,
                        revision_no=step.revision_no,
                    )
                )
    await session.flush()
    return {"checked": checked, "nudged": nudged}
