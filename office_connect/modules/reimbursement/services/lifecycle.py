"""Claim lifecycle — the SINGLE sanctioned mutation path onto the workflow engine.

workflow-standards.md §1: "a status column mutated by scattered code is
forbidden." This module is the one place reimbursement calls
``start_instance``/``execute_action``; every call syncs the denormalized
read-model (``status`` / ``holder_*`` / ``next_action`` + a
``reimb_status_histories`` row) in the SAME transaction, so the mirror can
never drift from the engine within a committed unit of work.

Everything here flushes and never commits (the module-wide contract shared by
``compute_claim_totals`` and ``allocate_reference_number``) — the caller owns
the transaction, which is exactly what makes submit atomic: totals + RB number
+ instance + status history commit or roll back together.

Holder doctrine (spec §7.1, delta register): the holder is a deterministic
WORK-MANAGEMENT pointer — whose inbox the item sits in, who the SLA ladder
nudges — never an authorization constraint (any permission-holder may still
act). Resolution is fail-closed: a gate with no resolvable scoped holder
refuses the transition rather than orphaning the claim with a null holder.

SLA doctrine (spec §7.4, delta register): gates are authored ``sla_hours=None``
and this module stamps ``step.sla_due_at`` itself in Manila WORKING days
(``sla.approval_working_days`` config, default 3) — the engine column counts
calendar hours and core-service #6 (the holiday calendar engine) already gives
us the working-day math. ``handed_to_fms`` is never stamped: the holder is
``external_fms`` and the ladder is holder-only (spec §7.5's >10-WD follow-up
is an Admin dashboard filter, not a notification).
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from decimal import Decimal
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core import workflow as wf
from office_connect.core.models import Staff, User, WorkflowInstance, WorkflowState
from office_connect.core.org_units import ancestors_or_self, authorize_scoped, permission_holders
from office_connect.core.reference_numbers import allocate_reference_number
from office_connect.core.session import set_audit_context
from office_connect.core.time import MANILA, to_manila, to_utc, utc_now
from office_connect.core.workdays import add_working_days, load_nonworking_dates
from office_connect.core.workflow.steps import gate_steps
from office_connect.modules.reimbursement.models import (
    ReimbClaim,
    ReimbConfig,
    ReimbReturnEvent,
    ReimbStatusHistory,
)
from office_connect.modules.reimbursement.services import errors
from office_connect.modules.reimbursement.services import status as st
from office_connect.modules.reimbursement.services.compute import compute_claim_totals
from office_connect.modules.reimbursement.workflow import (
    DEFINITION_CODE,
    FEATURE_FLAG_KEY,
    SUBJECT_KIND,
)
from office_connect.core.money import to_money

_ZERO = Decimal("0.00")
_CLAIM_ACTIONS = frozenset({"approve", "return", "resubmit", "cancel"})
_SLA_WD_KEY = "sla.approval_working_days"
_SLA_WD_DEFAULT = 3
_SLA_DUE_LOCAL_TIME = time(17, 0)  # end of the Manila working day


# --------------------------------------------------------------------------
# Lookups
# --------------------------------------------------------------------------


async def _locked_claim(session: AsyncSession, claim_id: int) -> ReimbClaim:
    """FOR UPDATE-lock the claim row — the double-submit/race serializer. Lock
    order is always claim → instance (``execute_action`` locks the instance),
    so every lifecycle path is deadlock-consistent."""
    claim = (
        await session.execute(
            select(ReimbClaim).where(ReimbClaim.id == claim_id).with_for_update()
        )
    ).scalar_one_or_none()
    if claim is None:
        raise errors.claim_not_found()
    return claim


async def _owner_user(session: AsyncSession, claimant_id: int) -> User | None:
    """The claimant's live login account (``core_users.staff_id`` bridge)."""
    return (
        await session.execute(
            select(User).where(
                User.staff_id == claimant_id, User.is_active.is_(True)
            )
        )
    ).scalar_one_or_none()


async def _is_owner(
    session: AsyncSession, claim: ReimbClaim, actor_user_id: int
) -> bool:
    actor = await session.get(User, actor_user_id)
    return bool(actor and actor.staff_id == claim.claimant_id)


async def config_working_days(
    session: AsyncSession, *, key: str, default: int, today
) -> int:
    """A ``{"working_days": n}`` config value as-of today (latest effective
    row). SLA cadence is a nudge, not money — a missing/malformed row falls
    back to the spec default rather than failing the transition (documented
    fail-soft; contrast the fail-closed money configs)."""
    rows = (
        (
            await session.execute(
                select(ReimbConfig).where(
                    ReimbConfig.key == key,
                    ReimbConfig.is_active.is_(True),
                    ReimbConfig.effective_from <= today,
                )
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return default
    latest = max(rows, key=lambda r: r.effective_from)
    try:
        return int(latest.value["working_days"])
    except (KeyError, TypeError, ValueError):
        return default


# --------------------------------------------------------------------------
# Holder resolution (spec §7.1 — one holder, always; fail-closed)
# --------------------------------------------------------------------------


async def resolve_holder(
    session: AsyncSession,
    *,
    state: WorkflowState,
    claim: ReimbClaim,
    instance: WorkflowInstance,
) -> tuple[str | None, int | None]:
    """Deterministic holder for ``state`` — ``(holder_kind, holder_id)``.

    - terminal → ``(None, None)`` (spec §6.1 shows "—"; §7.1 scopes the
      invariant to non-terminal states)
    - claimant-held (draft/returned) → the owner's user via the staff bridge,
      falling back to the instance originator (a claimant with no login)
    - external (handed_to_fms) → ``("external_fms", None)`` — the KIND carries
      the meaning; a NULL id with kind 'user' is the violation, not this
    - gate states → scoped holders of the gate's permission (global grants
      ignored so ``system_admin`` never becomes "the" holder), nearest org
      unit first, originator excluded under segregation, lowest user id as
      the tie-break; none → fail-closed ``reimb_no_eligible_holder``
    """
    if state.kind == "terminal":
        return (None, None)
    if state.code in st.CLAIMANT_STATES:
        owner = await _owner_user(session, claim.claimant_id)
        holder_id = owner.id if owner else instance.originator_user_id
        return ("user", holder_id)
    if state.code in st.EXTERNAL_STATES:
        return ("external_fms", None)

    holders = await permission_holders(
        session, state.required_permission, instance.org_unit_id
    )
    ancestry = await ancestors_or_self(session, instance.org_unit_id)
    proximity = {unit: rank for rank, unit in enumerate(ancestry)}
    candidates = sorted(
        (proximity[unit], user_id)
        for user_id, unit in holders
        if unit is not None
        and unit in proximity
        and not (
            state.enforce_segregation and user_id == instance.originator_user_id
        )
    )
    if not candidates:
        raise errors.no_eligible_holder(state.code)
    return ("user", candidates[0][1])


# --------------------------------------------------------------------------
# Read-model sync + SLA stamping (same transaction as the engine call)
# --------------------------------------------------------------------------


async def _sync_claim_from_event(
    session: AsyncSession,
    *,
    claim: ReimbClaim,
    event,
    now: datetime,
) -> None:
    """Mirror the engine event onto the claim. Partial approvals of a
    multi-slot gate emit a same-state event — those write NO history row and
    touch nothing (the slot progress lives in ``core_workflow_steps``)."""
    to_state = await session.get(WorkflowState, event.to_state_id)
    from_status = claim.status or st.DRAFT
    if to_state.code == from_status:
        return

    instance = await session.get(WorkflowInstance, claim.workflow_instance_id)
    holder_kind, holder_id = await resolve_holder(
        session, state=to_state, claim=claim, instance=instance
    )
    claim.status = to_state.code
    claim.holder_kind = holder_kind
    claim.holder_id = holder_id
    claim.holder_since = now if holder_kind is not None else None
    claim.next_action = st.NEXT_ACTION.get(to_state.code)
    session.add(
        ReimbStatusHistory(
            claim_id=claim.id,
            from_status=from_status,
            to_status=to_state.code,
            actor_id=event.actor_user_id,
            note=event.comment,
        )
    )
    await session.flush()


async def _stamp_sla(
    session: AsyncSession,
    *,
    claim: ReimbClaim,
    instance: WorkflowInstance,
    event,
    now: datetime,
) -> None:
    """Stamp working-day ``sla_due_at`` on freshly activated gate steps (the
    definition authors gates ``sla_hours=None`` — see the module docstring)."""
    state = await session.get(WorkflowState, event.to_state_id)
    if not state.is_approval_gate or state.code in st.EXTERNAL_STATES:
        return
    steps = await gate_steps(
        session,
        instance_id=instance.id,
        state_id=state.id,
        revision_no=instance.revision_no,
    )
    fresh = [s for s in steps if s.status == "active" and s.sla_due_at is None]
    if not fresh:
        return

    manila_today = to_manila(now).date()
    working_days = await config_working_days(
        session, key=_SLA_WD_KEY, default=_SLA_WD_DEFAULT, today=manila_today
    )
    # Window generously covers the worst holiday clustering around n WD.
    nonworking = await load_nonworking_dates(
        session, manila_today, manila_today + timedelta(days=working_days * 4 + 14)
    )
    due_date = add_working_days(manila_today, working_days, nonworking)
    due_at = to_utc(datetime.combine(due_date, _SLA_DUE_LOCAL_TIME, tzinfo=MANILA))
    for step in fresh:
        step.sla_due_at = due_at
    await session.flush()


# --------------------------------------------------------------------------
# Public lifecycle API
# --------------------------------------------------------------------------


async def submit_claim(
    session: AsyncSession,
    *,
    claim_id: int,
    actor_user_id: int,
    other_total: Decimal = _ZERO,
    idempotency_key: str | None = None,
    now: datetime | None = None,
) -> ReimbClaim:
    """First submit: totals + RB reference + workflow instance + status sync,
    one atomic transaction (flushes; the caller commits).

    Owner-only by decision (M3): with permission-based gates, segregation
    guards ``instance.originator_user_id`` as the maker — an on-behalf submit
    would guard the wrong person. On-behalf filing is a recorded deferral."""
    now = now or utc_now()
    set_audit_context(session, actor_id=actor_user_id)

    claim = await _locked_claim(session, claim_id)
    if claim.kind != "reimbursement":
        raise errors.claim_not_reimbursement()
    if claim.workflow_instance_id is not None:
        raise errors.claim_already_submitted()
    if not await _is_owner(session, claim, actor_user_id):
        raise errors.not_claim_owner()

    staff = await session.get(Staff, claim.claimant_id)
    org_unit_id = staff.section_id or staff.division_id if staff else None
    if org_unit_id is None:
        raise errors.claimant_no_org_unit()

    await compute_claim_totals(
        session, claim_id=claim.id, other_total=other_total,
        actor_user_id=actor_user_id,
    )
    # Flag gate fires inside start_instance — BEFORE a reference number is
    # burned (numbers are never reused, so order matters).
    instance = await wf.start_instance(
        session,
        definition_code=DEFINITION_CODE,
        actor_user_id=actor_user_id,
        org_unit_id=org_unit_id,
        subject_kind=SUBJECT_KIND,
        subject_id=claim.id,
        amount=to_money(claim.totals["grand"]),
        context={"claimant_user_id": actor_user_id},
        feature_flag_key=FEATURE_FLAG_KEY,
        now=now,
    )
    if claim.ref_no is None:
        claim.ref_no = await allocate_reference_number(
            session, scope="RB", year=to_manila(now).year
        )
    claim.workflow_instance_id = instance.id
    await session.flush()

    event = await wf.execute_action(
        session,
        instance_id=instance.id,
        action="submit",
        actor_user_id=actor_user_id,
        idempotency_key=idempotency_key
        or f"submit:{claim.id}:{instance.revision_no}",
        now=now,
    )
    await _sync_claim_from_event(session, claim=claim, event=event, now=now)
    await _stamp_sla(session, claim=claim, instance=instance, event=event, now=now)
    return claim


async def claim_action(
    session: AsyncSession,
    *,
    claim_id: int,
    action: str,
    actor_user_id: int,
    comment: str | None = None,
    reason_ids: Sequence[int] = (),
    idempotency_key: str | None = None,
    expected_version: int | None = None,
    now: datetime | None = None,
) -> ReimbClaim:
    """Act on a submitted claim (approve / return / resubmit / cancel) and sync
    the read-model in the same transaction. Engine guards (permission, comment,
    CAS, segregation, idempotency) all apply; the module adds the ownership
    belt on resubmit/cancel and the return-event record."""
    if action not in _CLAIM_ACTIONS:
        raise errors.unsupported_claim_action(action)
    now = now or utc_now()
    set_audit_context(session, actor_id=actor_user_id)

    claim = await _locked_claim(session, claim_id)
    if claim.workflow_instance_id is None:
        raise errors.claim_not_in_workflow()
    instance = await session.get(WorkflowInstance, claim.workflow_instance_id)

    if action in ("resubmit", "cancel"):
        # Belt to the engine's braces (FLAG 1): owner, or an admin reviewer.
        if not (
            await _is_owner(session, claim, actor_user_id)
            or await authorize_scoped(
                session, actor_user_id, "reimb.claim.review", instance.org_unit_id
            )
        ):
            raise errors.not_claim_owner()

    if action == "resubmit":
        # Fresh money after the fix-up — BEFORE routing, so future amount-tier
        # guards (definition v2) route on the recomputed grand total.
        await compute_claim_totals(
            session, claim_id=claim.id, actor_user_id=actor_user_id
        )
        instance.amount = to_money(claim.totals["grand"])
        await session.flush()

    event = await wf.execute_action(
        session,
        instance_id=instance.id,
        action=action,
        actor_user_id=actor_user_id,
        comment=comment,
        idempotency_key=idempotency_key
        or (
            f"{action}:{claim.id}:{instance.revision_no}"
            f":{instance.current_state_id}:{actor_user_id}"
        ),
        expected_version=expected_version,
        now=now,
    )

    if action == "return":
        to_state = await session.get(WorkflowState, event.to_state_id)
        # The engine stamps event.step_id only on approve (the acted slot); a
        # return resolves ALL live slots — recover the returned step here so
        # the learning-loop row points at the gate it bounced from.
        gate = await gate_steps(
            session,
            instance_id=instance.id,
            state_id=event.from_state_id,
            revision_no=event.revision_no,
        )
        returned_step_id = next(
            (s.id for s in gate if s.status == "returned"), None
        )
        session.add(
            ReimbReturnEvent(
                claim_id=claim.id,
                step_id=returned_step_id,
                reason_ids=list(reason_ids),
                free_comment=comment,
                returned_to=(
                    "claimant" if to_state.code == st.RETURNED else "previous_step"
                ),
            )
        )

    await _sync_claim_from_event(session, claim=claim, event=event, now=now)
    await _stamp_sla(session, claim=claim, instance=instance, event=event, now=now)
    return claim


async def cancel_draft_claim(
    session: AsyncSession,
    *,
    claim_id: int,
    actor_user_id: int,
    comment: str,
    now: datetime | None = None,
) -> ReimbClaim:
    """Cancel a claim that was never submitted (no instance exists — the
    engine's draft→cancelled transition is unreachable pre-submit). Owner-only;
    reason mandatory (spec §6.1 row 9). Still flows through this chokepoint so
    the status column is never mutated elsewhere."""
    now = now or utc_now()
    set_audit_context(session, actor_id=actor_user_id)

    claim = await _locked_claim(session, claim_id)
    if claim.workflow_instance_id is not None:
        raise errors.claim_already_submitted()
    if not await _is_owner(session, claim, actor_user_id):
        raise errors.not_claim_owner()
    if not comment:
        raise wf.errors.comment_required()

    from_status = claim.status or st.DRAFT
    claim.status = st.CANCELLED
    claim.holder_kind = None
    claim.holder_id = None
    claim.holder_since = None
    claim.next_action = None
    session.add(
        ReimbStatusHistory(
            claim_id=claim.id,
            from_status=from_status,
            to_status=st.CANCELLED,
            actor_id=actor_user_id,
            note=comment,
        )
    )
    await session.flush()
    return claim
