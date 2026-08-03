"""What may I do with this claim, and how late is it? — the approver read-model.

Two derivations the approval surface renders and the action endpoints
re-validate (workflow-standards §3: *the UI never computes permissions*):

1. ``claim_actions`` — the engine's ``available_actions``, plus the pre-instance
   answer the engine cannot give. A draft has no ``workflow_instance_id`` (the
   instance is created AT submit), so ``available_actions`` has nothing to
   compute over; the module synthesizes the owner's ``submit``/``cancel`` from
   the same rules ``submit_claim``/``cancel_draft_claim`` enforce.
2. ``claim_sla`` — the active gate step's ``sla_due_at`` and the spec §6.3
   derived badge. Derived SERVER-side and put on the wire as a state, not a
   raw timestamp for the browser to reason about: one implementation, one set
   of tests, one Manila-vs-UTC boundary.

Read-only — the caller owns the transaction.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core import workflow as wf
from office_connect.core.models import WorkflowInstance, WorkflowStep
from office_connect.core.time import utc_now
from office_connect.modules.reimbursement.models import ReimbClaim
from office_connect.modules.reimbursement.services import status as st
from office_connect.modules.reimbursement.services.lifecycle import is_claim_owner

# Spec §6.3: On Track / Due Soon / Overdue. "Due soon" is the last working day
# before the deadline — the §6.3 "≤ 7 days" window is keyed to the LIQUIDATION
# deadline (R-6, a 30-day clock); a 3-working-day approval SLA needs a tighter
# one or every item is born amber (delta register).
DUE_SOON_WINDOW = timedelta(days=1)

ON_TRACK = "on_track"
DUE_SOON = "due_soon"
OVERDUE = "overdue"


async def claim_actions(
    session: AsyncSession,
    *,
    claim: ReimbClaim,
    actor_user_id: int,
    now: datetime | None = None,
) -> list[str]:
    """The verbs this actor may POST against this claim right now."""
    if claim.workflow_instance_id is None:
        # Pre-instance: draft (or a never-submitted cancelled claim).
        if (claim.status or st.DRAFT) != st.DRAFT:
            return []
        if not await is_claim_owner(session, claim, actor_user_id):
            return []
        return ["submit", "cancel"]
    return await wf.available_actions(
        session,
        instance_id=claim.workflow_instance_id,
        actor_user_id=actor_user_id,
        now=now,
    )


def sla_state(due_at: datetime | None, *, now: datetime) -> str | None:
    """Spec §6.3's derived badge — never a status, always computed on view."""
    if due_at is None:
        return None
    if now > due_at:
        return OVERDUE
    if due_at - now <= DUE_SOON_WINDOW:
        return DUE_SOON
    return ON_TRACK


async def active_step_due_dates(
    session: AsyncSession, instance_ids: list[int]
) -> dict[int, datetime]:
    """instance_id → earliest active-step ``sla_due_at``, in ONE query.

    Covered by the partial index ``ix_core_workflow_steps_sla_due_at``
    (``WHERE status='active' AND sla_due_at IS NOT NULL``), so the My-Work
    badge join stays cheap no matter how long the inbox gets."""
    if not instance_ids:
        return {}
    rows = (
        await session.execute(
            select(WorkflowStep.instance_id, WorkflowStep.sla_due_at).where(
                WorkflowStep.instance_id.in_(instance_ids),
                WorkflowStep.status == "active",
                WorkflowStep.sla_due_at.is_not(None),
            )
        )
    ).all()
    earliest: dict[int, datetime] = {}
    for instance_id, due_at in rows:
        current = earliest.get(instance_id)
        if current is None or due_at < current:
            earliest[instance_id] = due_at
    return earliest


async def claim_sla(
    session: AsyncSession,
    *,
    claim: ReimbClaim,
    now: datetime | None = None,
) -> tuple[datetime | None, str | None]:
    """``(sla_due_at, sla_state)`` for one claim — the single-row form."""
    if claim.workflow_instance_id is None:
        return (None, None)
    due = (
        await active_step_due_dates(session, [claim.workflow_instance_id])
    ).get(claim.workflow_instance_id)
    return (due, sla_state(due, now=now or utc_now()))


async def instance_row_version(
    session: AsyncSession, claim: ReimbClaim
) -> int | None:
    """The CAS token the client echoes back as ``expected_version``
    (workflow-standards §4). NULL before submit — a draft has no instance."""
    if claim.workflow_instance_id is None:
        return None
    instance = await session.get(WorkflowInstance, claim.workflow_instance_id)
    return instance.row_version if instance is not None else None
