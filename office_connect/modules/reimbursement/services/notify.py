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
- The sweep **drains its work-list in keyset pages**, most-overdue-first. A
  single ``LIMIT`` ordered from one end is a starvation bug, not a budget: see
  ``sweep_sla_reminders`` for the full argument and the defect it fixes.

**Holder only, never superiors** (spec §7.4, non-negotiable): the recipient is
always ``claim.holder_id``; an ``external_fms`` holder is never nudged (spec
§7.5's >10-WD follow-up is the Admin queue filter, not a notification).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.email import EmailMessage
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
from office_connect.modules.reimbursement.models import ReimbCashAdvance, ReimbClaim
from office_connect.modules.reimbursement.services import status as st
from office_connect.modules.reimbursement.services.cash_advance import (
    UNLIQUIDATED_STATUSES,
    mark_overdue,
    overdue_note,
)
from office_connect.modules.reimbursement.services.lifecycle import (
    config_working_days,
    owner_user,
)
from office_connect.modules.reimbursement.workflow import SUBJECT_KIND

logger = logging.getLogger(__name__)

DEDUP_PREFIX = "reimb.claim.sla"
_REMINDER_KEY = "sla.reminder_repeat_days"
_REMINDER_DEFAULT = 2

#: Rows per query — bounds the statement and how long each row stays locked.
_PAGE_SIZE = 200
#: Runaway backstop. 200 × 50 = 10,000 overdue steps per beat, far beyond any
#: real agency's queue; hitting it is logged, never silently absorbed.
_MAX_PAGES = 50


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


async def _overdue_step_page(
    session: AsyncSession,
    *,
    now: datetime,
    page_size: int,
    after: tuple[datetime, int] | None,
) -> list[WorkflowStep]:
    """One keyset page of escalated, still-active reimbursement steps.

    Ordered **most-overdue-first** (spec §7.5's actual priority), with the step
    id as the tie-break so ``(sla_due_at, id)`` is a total order and the keyset
    cursor can neither skip a row nor serve one twice.
    """
    query = (
        select(WorkflowStep)
        .join(WorkflowInstance, WorkflowInstance.id == WorkflowStep.instance_id)
        .where(
            WorkflowStep.status == "active",
            WorkflowStep.escalation_level >= 1,
            WorkflowStep.sla_due_at.is_not(None),
            WorkflowStep.sla_due_at <= now,
            WorkflowInstance.subject_kind == SUBJECT_KIND,
        )
        .order_by(WorkflowStep.sla_due_at, WorkflowStep.id)
        .limit(page_size)
        .with_for_update(skip_locked=True, of=WorkflowStep)
    )
    if after is not None:
        query = query.where(
            tuple_(WorkflowStep.sla_due_at, WorkflowStep.id) > after
        )
    return list((await session.execute(query)).scalars().all())


async def sweep_sla_reminders(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    page_size: int = _PAGE_SIZE,
    max_pages: int = _MAX_PAGES,
) -> dict[str, int]:
    """The repeating ladder: for every escalated, still-active reimbursement
    step, send the k-th nudge once ``k * repeat`` working days have passed
    since the SLA fell due. Also the missed-first-nudge backstop (``k=0``).
    Flushes; the caller (ops task) commits.

    **The work-list is DRAINED in keyset pages, not truncated at one.** The
    first cut took ``ORDER BY id ASC LIMIT 200``, which is a budget that always
    starts at the same end of the queue: once ~200 steps are permanently stuck,
    every newly-overdue item sits behind them forever and is never nudged —
    the exact opposite of spec §7.5. Ordering most-overdue-first fixes the
    *priority*; only draining fixes the *starvation*, because the newest
    overdue item is by definition the least overdue and would otherwise be last
    in line under either ordering.

    ``page_size`` bounds each query (and how long a row stays locked);
    ``max_pages`` is the runaway backstop. Exhausting it is logged, never
    silent — a truncated sweep that looks identical to a complete one is how a
    reminder ladder quietly stops reminding.
    """
    now = now or utc_now()
    today = to_manila(now).date()

    repeat = await config_working_days(
        session, key=_REMINDER_KEY, default=_REMINDER_DEFAULT, today=today
    )
    checked = nudged = 0
    cursor: tuple[datetime, int] | None = None
    drained = False

    for _ in range(max_pages):
        steps = await _overdue_step_page(
            session, now=now, page_size=page_size, after=cursor
        )
        if not steps:
            drained = True
            break
        cursor = (steps[-1].sla_due_at, steps[-1].id)

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
            notification_id = await _send_nudge(
                session, claim=claim, step=step, k=k
            )
            if notification_id is not None:
                nudged += 1
                if k > 0:
                    # The decision-trail row for a repeat nudge (the escalation
                    # partial-unique index constrains event_type='escalation'
                    # only; dedup above guarantees one event per (step, k)).
                    session.add(
                        WorkflowEvent(
                            instance_id=instance.id,
                            step_id=step.id,
                            event_type="reminder",
                            escalation_level=k,
                            revision_no=step.revision_no,
                        )
                    )
        if len(steps) < page_size:
            drained = True
            break

    if not drained:
        logger.warning(
            "SLA reminder sweep hit its page budget — some overdue steps were "
            "not examined this beat and will be picked up on the next run",
            extra={
                "checked": checked,
                "nudged": nudged,
                "page_size": page_size,
                "max_pages": max_pages,
            },
        )

    await session.flush()
    return {"checked": checked, "nudged": nudged, "drained": drained}


# --------------------------------------------------------------------------
# R-6-clock — the liquidation deadline ladder (spec §12)
# --------------------------------------------------------------------------

LIQUIDATION_DEDUP_PREFIX = "reimb.liquidation.deadline"

#: Spec §12 row: "Liquidation D-7 / D-3 / D-0 / overdue → Claimant (CA holder)".
#: Evaluated as "the most urgent threshold REACHED", not "days_remaining ==
#: exactly n": a beat that missed a day (worker restart, holiday outage) must
#: still warn, and it must warn at the level that is now true. Sending "7 days
#: left" on the day 3 remain would be worse than sending nothing.
_MILESTONES: tuple[tuple[int, str], ...] = (
    (0, "d0"),
    (3, "d3"),
    (7, "d7"),
)

#: Spec §12: "email only for liquidation D-3/D-0 (transactional)". The overdue
#: repeats stay in-app — read literally, and defensibly: a daily email about a
#: deadline already missed trains people to filter the sender.
_EMAIL_MILESTONES = frozenset({"d3", "d0"})

#: These carry a legal consequence, so they bypass notification opt-outs
#: (``_PREFS_BYPASS_CLASSES`` in core/notifications/recipients.py). A traveller
#: may mute workflow chatter; they may not mute COA telling them their salary is
#: about to be deducted.
_LIQUIDATION_CLASS = "transactional"


def _liquidation_dedup_key(cash_advance_id: int, token: str, channel: str) -> str:
    """One key per (advance, rung, CHANNEL).

    ``token`` is the LADDER RUNG, not the milestone kind: the D-rungs are
    ``d7``/``d3``/``d0`` and each fires once, while the overdue rung repeats and
    carries its index (``overdue:0``, ``overdue:1``, …) so each repeat is a
    distinct key. The channel is in the key because D-3 and D-0 send twice —
    in-app AND email — and without it the second row would dedup away against
    the first, so the email spec §12 promises would silently never arrive.
    """
    return f"{LIQUIDATION_DEDUP_PREFIX}:{cash_advance_id}:{token}:{channel}"


def _milestone_for(remaining: int) -> str | None:
    """The most urgent D-milestone reached at ``remaining`` days, or None."""
    if remaining < 0:
        return None  # past the deadline — the repeating overdue ladder owns it
    for threshold, name in _MILESTONES:
        if remaining <= threshold:
            return name
    return None


def _liquidation_body(
    *,
    advance: ReimbCashAdvance,
    milestone: str,
    remaining: int,
    note: str | None,
) -> tuple[str, str]:
    """``(subject, body)`` in plain language — spec §9.1 principle 3 + 4.

    Every variant says what to do next, and the D-0/overdue variants carry the
    COA consequence copy from config VERBATIM (``liquidation.overdue_note``) —
    the resident COA auditor owns that sentence, not this module.
    """
    which = f"cash advance {advance.dv_no}" if advance.dv_no else "cash advance"
    due = advance.deadline_date.isoformat() if advance.deadline_date else "soon"
    amount = f"₱{advance.amount:,.2f}"

    if milestone == "overdue":
        subject = f"Overdue: liquidate your {which}"
        body = (
            f"Your {which} of {amount} was due for liquidation on {due} and is "
            f"now {abs(remaining)} day(s) overdue. File your liquidation report "
            "as soon as possible."
        )
    elif milestone == "d0":
        subject = f"Due today: liquidate your {which}"
        body = (
            f"Your {which} of {amount} must be liquidated today ({due}). File "
            "your liquidation report now."
        )
    else:
        days = "3 days" if milestone == "d3" else "7 days"
        subject = f"Liquidate your {which} within {days}"
        body = (
            f"Your {which} of {amount} must be liquidated by {due} — "
            f"{remaining} day(s) left. Prepare your liquidation report."
        )

    if note and milestone in ("d0", "overdue"):
        body = f"{body} {note}"
    return (subject, body)


async def _send_liquidation_nudge(
    session: AsyncSession,
    *,
    advance: ReimbCashAdvance,
    recipient_user_id: int,
    recipient_email: str | None,
    milestone: str,
    token: str,
    remaining: int,
    note: str | None,
) -> int:
    """Persist the in-app nudge, plus the email at D-3/D-0. Returns rows written.

    ``milestone`` is the KIND (``d7``/``d3``/``d0``/``overdue``) — it decides the
    copy and whether an email goes out. ``token`` is the ladder RUNG and decides
    idempotency; the two differ only for the repeating overdue rung.
    """
    subject, body = _liquidation_body(
        advance=advance, milestone=milestone, remaining=remaining, note=note
    )
    written = 0

    in_app_key = _liquidation_dedup_key(advance.id, token, "in_app")
    if not await _already_sent(session, in_app_key):
        notification_id = await persist_notification(
            session,
            Notification(
                channel="in_app",
                meta={
                    "dedup_key": in_app_key,
                    "recipient_user_id": recipient_user_id,
                    "module": "reimbursement",
                    "kind": "liquidation_deadline",
                    "notification_class": _LIQUIDATION_CLASS,
                    "cash_advance_id": advance.id,
                    "milestone": milestone,
                    "subject": subject,
                    "body_text": body,
                },
            ),
        )
        dispatch_on_commit(session, notification_id)
        written += 1

    # Email needs a real address up front: EmailMessage refuses an empty `to`,
    # so an unresolvable claimant gets the in-app nudge and nothing else rather
    # than raising and losing the whole sweep.
    if milestone in _EMAIL_MILESTONES and recipient_email:
        email_key = _liquidation_dedup_key(advance.id, token, "email")
        if not await _already_sent(session, email_key):
            notification_id = await persist_notification(
                session,
                Notification(
                    channel="email",
                    email=EmailMessage(
                        to=[recipient_email], subject=subject, text_body=body
                    ),
                    meta={
                        "dedup_key": email_key,
                        "recipient_user_id": recipient_user_id,
                        "module": "reimbursement",
                        "kind": "liquidation_deadline",
                        "notification_class": _LIQUIDATION_CLASS,
                        "cash_advance_id": advance.id,
                        "milestone": milestone,
                    },
                ),
            )
            dispatch_on_commit(session, notification_id)
            written += 1

    return written


async def sweep_liquidation_reminders(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    page_size: int = _PAGE_SIZE,
    max_pages: int = _MAX_PAGES,
) -> dict[str, int]:
    """The D-7 / D-3 / D-0 / overdue ladder for unliquidated cash advances.

    Spec §6.2 starts this clock at ``cash_advance.date_return`` and §12 routes
    every rung to the CLAIMANT (the advance's holder) — never a superior, the
    same non-negotiable that governs the approval ladder. The advance's own
    ``status`` flips to ``overdue`` in the same pass: §6.3's *"Overdue is a
    derived badge, never a status"* governs the CLAIM, while §5.4 gives the cash
    advance a real ``overdue`` value, because COA asks for the count and peso
    total of overdue advances (spec §13) and a derived badge cannot be summed.

    Drained in keyset pages, most-urgent-first — written this way from the start
    rather than inheriting the single-``LIMIT`` starvation the SLA ladder had to
    have fixed out of it. Flushes; the caller (ops task) commits.
    """
    now = now or utc_now()
    today = to_manila(now).date()

    repeat = await config_working_days(
        session, key=_REMINDER_KEY, default=_REMINDER_DEFAULT, today=today
    )
    note = await overdue_note(session, today=today)
    horizon = today + timedelta(days=_MILESTONES[-1][0])

    checked = nudged = flipped = 0
    cursor: tuple[date, int] | None = None
    drained = False

    for _ in range(max_pages):
        query = (
            select(ReimbCashAdvance)
            .where(
                ReimbCashAdvance.status.in_(UNLIQUIDATED_STATUSES),
                ReimbCashAdvance.deadline_date.is_not(None),
                ReimbCashAdvance.deadline_date <= horizon,
            )
            .order_by(ReimbCashAdvance.deadline_date, ReimbCashAdvance.id)
            .limit(page_size)
            .with_for_update(skip_locked=True)
        )
        if cursor is not None:
            query = query.where(
                tuple_(
                    ReimbCashAdvance.deadline_date, ReimbCashAdvance.id
                ) > cursor
            )
        advances = list((await session.execute(query)).scalars().all())
        if not advances:
            drained = True
            break
        cursor = (advances[-1].deadline_date, advances[-1].id)

        for advance in advances:
            checked += 1
            owner = await owner_user(session, advance.claimant_id)
            remaining = (advance.deadline_date - today).days

            if remaining < 0:
                # Past the deadline: flip the record, then nudge on the repeat
                # cadence. The flip happens even when there is no login to
                # notify — the overdue COUNT is a financial fact about the
                # advance, independent of whether anyone can be emailed.
                if await mark_overdue(
                    session, cash_advance=advance, actor_user_id=None
                ):
                    flipped += 1
                # Nudge cadence counts WORKING days even though the deadline
                # itself is calendar: when something is due and how often we
                # chase it are different questions, and nobody should be
                # nagged on a Sunday. Same split the SLA ladder already makes.
                nonworking = await load_nonworking_dates(
                    session, advance.deadline_date, today
                )
                overdue_wd = working_days_between(
                    advance.deadline_date, today, nonworking
                )
                k = overdue_wd // repeat if repeat > 0 else 0
                milestone, token = "overdue", f"overdue:{k}"
            else:
                found = _milestone_for(remaining)
                if found is None:
                    continue
                milestone = token = found

            if owner is None:
                continue  # no login to address — the flip above still stands
            nudged += await _send_liquidation_nudge(
                session,
                advance=advance,
                recipient_user_id=owner.id,
                recipient_email=owner.email,
                milestone=milestone,
                token=token,
                remaining=remaining,
                note=note,
            )

        if len(advances) < page_size:
            drained = True
            break

    if not drained:
        logger.warning(
            "Liquidation reminder sweep hit its page budget — some advances "
            "were not examined this beat",
            extra={"checked": checked, "page_size": page_size, "max_pages": max_pages},
        )

    await session.flush()
    return {
        "checked": checked,
        "nudged": nudged,
        "flipped_overdue": flipped,
        "drained": drained,
    }
