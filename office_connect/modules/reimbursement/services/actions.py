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
from office_connect.core.org_units import authorize_scoped
from office_connect.core.time import utc_now
from office_connect.modules.reimbursement.models import ReimbCashAdvance, ReimbClaim
from office_connect.modules.reimbursement.services import cash_advance as ca
from office_connect.modules.reimbursement.services import checklist
from office_connect.modules.reimbursement.services import settlement
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

#: The liquidation chain's terminal verb (R-6-liq-settle). NOT an engine action —
#: the graph still authors ``approve`` at ``handed_to_fms``, and the engine still
#: authorizes it. This is the client-facing name for "clear that gate, and record
#: the money while you do", which is a different ROUTE
#: (``POST /claims/{id}/settle``) driving the same transition.
SETTLE = "settle"

#: The reimbursement chain's terminal verb (R-7-events) — the same rewrite, one
#: chain over: ``POST /claims/{id}/mark-paid`` clears ``handed_to_fms`` while
#: recording the payment reference spec §6.1 row 8 asks for.
MARK_PAID = "mark_paid"

#: The FMS status relay (R-7-events). Not a transition at all — it appends to
#: ``reimb_external_events`` and moves nothing — but it rides the action set for
#: the ``SPAWN`` reason: that set is the client's ONLY sanctioned answer to "what
#: may I do here" (workflow-standards §3), and the alternative is a browser
#: inferring a permission from a role name.
RELAY = "relay_fms"

#: Spec §3.2's "Set external FMS statuses → Admin Officer, System Admin", as the
#: permission string the grant data actually carries. Same constant as
#: ``workflow.FMS_PERM``, spelled here rather than imported: importing the
#: workflow module from this one would pull the definition seeder into every
#: request that renders a button.
FMS_UPDATE_PERM = "reimb.claim.fms_update"

#: Which client verb replaces ``approve`` at ``handed_to_fms``, by claim kind.
#: Both chains end at a state that must record data, so on both the bare verb is
#: certain to fail (``lifecycle``'s two chokepoints) while the actor IS
#: authorized to clear the gate — so the verb is REWRITTEN, never dropped, and
#: the table is what stops the two chains' answers from drifting apart.
_TERMINAL_VERB: dict[str, str] = {
    st.LIQUIDATION_KIND: SETTLE,
    st.REIMBURSEMENT_KIND: MARK_PAID,
}

#: Spec §6.2's "one tap": claim the difference an over-advance left owing. Also
#: not an engine action — it happens AFTER the chain is terminal, and it creates
#: a new claim rather than moving this one. It belongs in the action set anyway,
#: because that set is the client's only sanctioned answer to "what may I do
#: here" (workflow-standards §3), and the alternative — letting the browser
#: infer ownership from a claimant id — is the client computing permissions.
SPAWN = "spawn"


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
        # `submit` stays on offer even with an incomplete packet: the Review
        # step renders the button plus the blocking list inline (spec §9.3 step
        # 5), so withholding the verb would make the goal invisible. `approve`
        # is the opposite case — see below.
        return ["submit", "cancel"]

    verbs = await wf.available_actions(
        session,
        instance_id=claim.workflow_instance_id,
        actor_user_id=actor_user_id,
        now=now,
    )
    if "approve" in verbs and not await checklist.persisted_packet_complete(
        session, claim=claim
    ):
        # The R-4-screens doctrine again: never offer a button certain to fail.
        # The approver sees a red callout explaining the gap instead, and
        # `return` — their actual remedy — is untouched.
        verbs = [verb for verb in verbs if verb != "approve"]
    if "approve" in verbs and (claim.status or st.DRAFT) == st.HANDED_TO_FMS:
        # Same doctrine, one step further (R-6-liq-settle, then R-7-events). A
        # bare approve here is certain to fail — lifecycle's two chokepoints
        # refuse it — but the actor IS authorized to clear this gate; they just
        # have to record the facts while doing it. So the verb is REWRITTEN
        # rather than dropped: dropping it would leave a hole where the approver
        # needs a button, and `settle`/`mark_paid` is that button. `return` (FMS
        # bouncing the packet back) is untouched on both chains.
        terminal = _TERMINAL_VERB.get(claim.kind or st.REIMBURSEMENT_KIND)
        if terminal is not None:
            verbs = [terminal if verb == "approve" else verb for verb in verbs]
    if await _can_relay(session, claim=claim, actor_user_id=actor_user_id):
        verbs = [*verbs, RELAY]
    if await _can_spawn(session, claim=claim, actor_user_id=actor_user_id):
        verbs = [*verbs, SPAWN]
    return verbs


async def _can_relay(
    session: AsyncSession, *, claim: ReimbClaim, actor_user_id: int
) -> bool:
    """May this actor relay what FMS says about this claim?

    Mirrors ``api/external.py``'s own guard exactly — the claim is with FMS, and
    the actor's ``reimb.claim.fms_update`` grant covers its org unit (spec §3.2:
    "Set external FMS statuses → Admin Officer, System Admin"). Duplicating the
    rule here is the price of the R-4-screens doctrine: the button must not be
    offered to someone certain to get a 403, and the service must not trust the
    button. Both, or neither is safe — the ``_can_spawn`` precedent.

    Deliberately NOT keyed on holding the *engine's* gate authorization: the
    relay is not a transition, so ``available_actions`` has nothing to say about
    it, and an FMS-held claim's engine gate answers a different question.

    The org unit is read straight off the instance rather than through
    ``deps.claim_org_unit``: a claim at ``handed_to_fms`` is submitted by
    definition, so that helper's unsubmitted fallback is unreachable here — and
    reaching from a service into the API layer to borrow it would invert the
    dependency the whole module is arranged around.
    """
    if (claim.status or st.DRAFT) != st.HANDED_TO_FMS:
        return False
    if claim.workflow_instance_id is None:
        return False
    instance = await session.get(WorkflowInstance, claim.workflow_instance_id)
    if instance is None or instance.org_unit_id is None:
        return False
    return await authorize_scoped(
        session, actor_user_id, FMS_UPDATE_PERM, instance.org_unit_id
    )


async def _can_spawn(
    session: AsyncSession, *, claim: ReimbClaim, actor_user_id: int
) -> bool:
    """May this actor claim the difference an over-advance left owing?

    Mirrors ``settlement.spawn_reimbursement``'s own guards exactly — a settled
    liquidation, the ``over_advance`` mode, no live spawn already, and the
    CLAIMANT asking. Duplicating them here is the price of the R-4-screens
    doctrine: the button must not be offered to someone certain to get a 403,
    and the service must not trust the button. Both, or neither is safe.
    """
    if claim.kind != st.LIQUIDATION_KIND:
        return False
    if (claim.status or st.DRAFT) != st.SETTLED:
        return False
    if not await is_claim_owner(session, claim, actor_user_id):
        return False
    if claim.cash_advance_id is None:
        return False
    advance = await session.get(ReimbCashAdvance, claim.cash_advance_id)
    if advance is None or advance.settlement_mode != ca.OVER_ADVANCE:
        return False
    return await settlement.spawn_for_liquidation(session, claim.id) is None


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
