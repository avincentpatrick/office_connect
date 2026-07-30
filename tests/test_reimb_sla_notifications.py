"""R-4-app QA gate: working-day SLA stamping + holder-only escalation delivery.

Spec §7.4 (non-negotiable): due in ``sla.approval_working_days`` (3) WORKING
days, one nudge at the SLA, a repeat every ``sla.reminder_repeat_days`` (2)
working days — TO THE HOLDER ONLY, never superiors. The engine column is
calendar hours, so the module stamps ``sla_due_at`` itself (Manila working
days); the engine sweep escalates once; the ops ladder repeats. Every path is
idempotent via outbox dedup keys.

Assertions target SPECIFIC step ids/dedup keys — the shared dev DB carries
benign steps from other tests, so global counts would be fragile.
"""

from datetime import date, datetime, timezone

from sqlalchemy import select

from office_connect.core import workflow as wf
from office_connect.core.models import Holiday, WorkflowEvent, WorkflowStep
from office_connect.core.models.notification import NotificationOutbox
from office_connect.core.workflow import sla as wf_sla
from office_connect.modules.reimbursement.services import status as st
from office_connect.modules.reimbursement.services.lifecycle import (
    claim_action,
    submit_claim,
)
from office_connect.modules.reimbursement.services.notify import (
    notify_escalation,
    sweep_sla_reminders,
)
from tests.reimb_lifecycle_helpers import standard_cast
from tests.workflow_helpers import build_chain

UTC = timezone.utc


async def _clear_holidays(session, start: date, end: date) -> None:
    """Deactivate any holiday rows in the window — the suite leaves committed
    rows behind (a prior run's injected holiday would silently shift every
    absolute working-day expectation below). No hard deletes, ever."""
    rows = (
        (
            await session.execute(
                select(Holiday).where(
                    Holiday.calendar_date >= start,
                    Holiday.calendar_date <= end,
                    Holiday.is_active.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        row.is_active = False
    await session.flush()


async def _sweep_until_escalated(session, step, *, now) -> None:
    """Drain the sweep until OUR step escalates — the shared dev DB carries
    past-due steps from other tests, and each sweep pass is LIMIT-bounded."""
    for _ in range(50):
        if (step.escalation_level or 0) >= 1:
            return
        result = await wf_sla.sweep_due_steps(session, now=now, limit=500)
        if result["escalated"] == 0:
            break
    assert (step.escalation_level or 0) >= 1, "step never escalated"


async def _division_steps(session, claim):
    return (
        (
            await session.execute(
                select(WorkflowStep).where(
                    WorkflowStep.instance_id == claim.workflow_instance_id,
                    WorkflowStep.status == "active",
                )
            )
        )
        .scalars()
        .all()
    )


async def test_sla_stamped_in_manila_working_days(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    # Own calendar week: Mon 2027-03-01 10:00 Manila (02:00 UTC), window cleared.
    await _clear_holidays(app_session, date(2027, 2, 22), date(2027, 3, 14))
    cast = await standard_cast(app_session, make_user)
    claim = await submit_claim(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.owner.id,
        now=datetime(2027, 3, 1, 2, 0, tzinfo=UTC),
    )
    (step,) = await _division_steps(app_session, claim)
    # 3 WD after Mon 03-01 → Thu 03-04, 17:00 Manila = 09:00 UTC. Weekends
    # never count (a 72-hour stamp would have said Thu 10:00 Manila).
    assert step.sla_due_at == datetime(2027, 3, 4, 9, 0, tzinfo=UTC)


async def test_sla_stamp_respects_seeded_holidays(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    # Own calendar week: Mon 2027-04-05, with Tue 04-06 injected as a holiday.
    # Unique name per run — (calendar_date, name, scope) is unique and the
    # suite leaves committed rows behind; _clear_holidays only deactivates.
    import secrets

    await _clear_holidays(app_session, date(2027, 3, 29), date(2027, 4, 18))
    app_session.add(
        Holiday(
            calendar_date=date(2027, 4, 6),
            name=f"Test Holiday R-4-app {secrets.token_hex(4)}",
            holiday_type="regular", is_active=True,
        )
    )
    await app_session.flush()

    cast = await standard_cast(app_session, make_user)
    claim = await submit_claim(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.owner.id,
        now=datetime(2027, 4, 5, 2, 0, tzinfo=UTC),
    )
    (step,) = await _division_steps(app_session, claim)
    # Tue is non-working → Tue,Wed,Thu shifts to Wed,Thu,Fri 04-09.
    assert step.sla_due_at == datetime(2027, 4, 9, 9, 0, tzinfo=UTC)


async def test_handed_to_fms_is_never_stamped(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    cast = await standard_cast(app_session, make_user)
    claim = await submit_claim(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.owner.id,
    )
    await claim_action(app_session, claim_id=claim.id, action="approve", actor_user_id=cast.approver.id)
    await claim_action(app_session, claim_id=claim.id, action="approve", actor_user_id=cast.admin.id)
    assert claim.status == st.HANDED_TO_FMS

    steps = await _division_steps(app_session, claim)
    assert steps and all(s.sla_due_at is None for s in steps)
    # external_fms holds the ball; the ladder is holder-only → no nudge target.


async def test_escalation_notifies_holder_only_and_dedups(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    # Own calendar week: Mon 2027-05-03 → due Thu 05-06; sweep Fri 05-07.
    await _clear_holidays(app_session, date(2027, 4, 26), date(2027, 5, 16))
    cast = await standard_cast(app_session, make_user)
    claim = await submit_claim(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.owner.id,
        now=datetime(2027, 5, 3, 2, 0, tzinfo=UTC),
    )
    (step,) = await _division_steps(app_session, claim)

    # Before any escalation: the defensive no-op (the enqueuer seam fires
    # pre-commit inside the sweep tx — a task may look too early).
    assert await notify_escalation(app_session, step_id=step.id) is None

    captured: list[int] = []
    wf_sla.register_sla_enqueuer(captured.append)
    try:
        await _sweep_until_escalated(
            app_session, step, now=datetime(2027, 5, 7, 0, 0, tzinfo=UTC)
        )
    finally:
        wf_sla.register_sla_enqueuer(None)
    assert step.id in captured

    first = await notify_escalation(app_session, step_id=step.id)
    assert first is not None
    second = await notify_escalation(app_session, step_id=step.id)
    assert second is None  # dedup — one first-nudge, ever

    row = (
        await app_session.execute(
            select(NotificationOutbox).where(
                NotificationOutbox.dedup_key == f"reimb.claim.sla:{step.id}:0"
            )
        )
    ).scalar_one()
    assert row.channel == "in_app"
    assert row.recipient_user_id == cast.approver.id  # the HOLDER — nobody else
    assert row.module == "reimbursement"
    assert claim.ref_no in row.subject


async def test_reminder_ladder_counts_working_days(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    # Own calendar week: Mon 2027-06-07 → due Thu 06-10.
    await _clear_holidays(app_session, date(2027, 5, 31), date(2027, 6, 20))
    cast = await standard_cast(app_session, make_user)
    claim = await submit_claim(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.owner.id,
        now=datetime(2027, 6, 7, 2, 0, tzinfo=UTC),
    )
    (step,) = await _division_steps(app_session, claim)

    wf_sla.register_sla_enqueuer(None)
    await _sweep_until_escalated(
        app_session, step, now=datetime(2027, 6, 11, 0, 0, tzinfo=UTC)
    )

    # Thu 06-10 due → Thu 06-17 is 5 WD later → k = 5 // 2 = 2.
    ladder_now = datetime(2027, 6, 17, 2, 0, tzinfo=UTC)
    await sweep_sla_reminders(app_session, now=ladder_now)
    key = f"reimb.claim.sla:{step.id}:2"
    row = (
        await app_session.execute(
            select(NotificationOutbox).where(NotificationOutbox.dedup_key == key)
        )
    ).scalar_one()
    assert row.recipient_user_id == cast.approver.id

    reminder_events = (
        await app_session.execute(
            select(WorkflowEvent).where(
                WorkflowEvent.step_id == step.id,
                WorkflowEvent.event_type == "reminder",
            )
        )
    ).scalars().all()
    assert [e.escalation_level for e in reminder_events] == [2]

    # Same day, second beat firing: fully idempotent for this step.
    await sweep_sla_reminders(app_session, now=ladder_now)
    rows = (
        await app_session.execute(
            select(NotificationOutbox).where(NotificationOutbox.dedup_key == key)
        )
    ).scalars().all()
    assert len(rows) == 1


async def test_ladder_ignores_non_reimbursement_subjects(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    """The seam stays engine-generic: a foreign definition's escalated step
    never produces a reimbursement nudge."""
    staff, _ = await make_user(roles=("staff",))
    approver, _ = await make_user(roles=("approver",))
    chain = await build_chain(app_session, sla_hours=1)
    inst = await wf.start_instance(
        app_session, definition_code=chain.definition.code, actor_user_id=staff.id
    )
    await wf.execute_action(
        app_session, instance_id=inst.id, action="submit", actor_user_id=staff.id
    )
    foreign_step = (
        await app_session.execute(
            select(WorkflowStep).where(WorkflowStep.instance_id == inst.id)
        )
    ).scalar_one()

    wf_sla.register_sla_enqueuer(None)
    await _sweep_until_escalated(
        app_session, foreign_step, now=datetime(2027, 7, 5, 0, 0, tzinfo=UTC)
    )
    assert await notify_escalation(app_session, step_id=foreign_step.id) is None

    await sweep_sla_reminders(app_session, now=datetime(2027, 7, 12, 2, 0, tzinfo=UTC))
    rows = (
        await app_session.execute(
            select(NotificationOutbox).where(
                NotificationOutbox.dedup_key.like(
                    f"reimb.claim.sla:{foreign_step.id}:%"
                )
            )
        )
    ).scalars().all()
    assert rows == []
