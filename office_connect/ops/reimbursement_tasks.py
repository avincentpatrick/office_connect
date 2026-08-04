"""Reimbursement SLA delivery — the enqueuer registration + the reminder ladder.

R-4-app closes the loop `ops/workflow_tasks.py` left open: the engine sweep
escalates an overdue step once and calls the enqueuer registered here; the
daily ladder task repeats the nudge every ``sla.reminder_repeat_days`` working
days — **to the holder only, never superiors** (spec §7.4, non-negotiable).

Two timing subtleties, both by design:
- ``register_sla_enqueuer``'s callable fires INSIDE the sweep's transaction
  (after flush, before commit), so ``ops.notify_workflow_escalation`` may start
  before the escalation row is visible. The task re-reads committed state in
  its own session (the ``notify_escalation`` service is defensive) and retries
  briefly; the ladder's ``k=0`` dedup key is the final backstop for anything
  that still slips through — every path is idempotent.
- The ladder runs daily (08:30 Manila): nudge cadence is day-granular working
  days, so an hourly/5-min beat would only burn no-op queries.

Same async-in-worker discipline as ``ops/workflow_tasks.py`` (fresh NullPool
engine + ``OCSession`` listeners, disposed in ``finally``).
"""

from __future__ import annotations

import asyncio
from typing import Any

# Registering these installs the OCSession audit + soft-delete listeners.
import office_connect.core.audit  # noqa: F401
import office_connect.core.soft_delete  # noqa: F401
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from office_connect.core.config import get_settings
from office_connect.core.session import OCSession, set_audit_context
from office_connect.core.workflow import register_sla_enqueuer
from office_connect.modules.reimbursement.services.notify import (
    notify_escalation,
    sweep_liquidation_reminders,
    sweep_sla_reminders,
)
from office_connect.worker import celery_app


async def _with_app_session(work, *, request_id: str) -> Any:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        sync_session_class=OCSession,
        expire_on_commit=False,
    )
    try:
        async with factory() as session:
            set_audit_context(session, request_id=request_id)
            result = await work(session)
            await session.commit()
            return result
    finally:
        await engine.dispose()


@celery_app.task(
    name="ops.notify_workflow_escalation", bind=True, acks_late=True, max_retries=3
)
def notify_workflow_escalation(self, step_id: int) -> dict[str, Any]:
    """Deliver the first holder nudge for an escalated step."""
    notification_id = asyncio.run(
        _with_app_session(
            lambda s: notify_escalation(s, step_id=step_id),
            request_id="workflow-sla-notify",
        )
    )
    if notification_id is None and self.request.retries < self.max_retries:
        # Pre-commit race (see module docstring) — or a legitimate no-op
        # (non-reimb subject / external holder / already sent). Retries are
        # cheap and idempotent; the daily ladder is the final backstop.
        raise self.retry(countdown=30)
    return {"step_id": step_id, "notification_id": notification_id}


@celery_app.task(name="ops.reimb_sla_reminders", bind=True, acks_late=True)
def reimb_sla_reminders(self, page_size: int = 200) -> dict[str, Any]:
    """The repeating holder-only ladder (beat: daily 08:30 Asia/Manila).

    ``page_size`` bounds each query, not the whole beat — the sweep drains its
    work-list across pages so a backlog can never starve newly-overdue items.
    """
    return asyncio.run(
        _with_app_session(
            lambda s: sweep_sla_reminders(s, page_size=page_size),
            request_id="reimb-sla-ladder",
        )
    )


@celery_app.task(name="ops.reimb_liquidation_reminders", bind=True, acks_late=True)
def reimb_liquidation_reminders(self, page_size: int = 200) -> dict[str, Any]:
    """The COA 30-day liquidation ladder — D-7 / D-3 / D-0 / overdue.

    Beat: daily 08:35 Asia/Manila. Day-granular by nature (a deadline moves once
    per day), and idempotent through outbox dedup keys, so a missed or repeated
    beat costs nothing. Also the writer that flips an advance past its deadline
    to ``overdue`` — spec §5.4's status, which spec §13's "overdue CAs count + ₱"
    report has to be able to sum.
    """
    return asyncio.run(
        _with_app_session(
            lambda s: sweep_liquidation_reminders(s, page_size=page_size),
            request_id="reimb-liquidation-ladder",
        )
    )


# ops → core injection (the exact shape of ops/notification_tasks.py): the
# engine sweep hands escalated step ids to the worker through this seam.
register_sla_enqueuer(
    lambda step_id: celery_app.send_task(
        "ops.notify_workflow_escalation", args=[step_id]
    )
)
