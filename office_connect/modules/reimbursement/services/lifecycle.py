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
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core import workflow as wf
from office_connect.core.documents import generate_on_commit
from office_connect.core.models import (
    Staff,
    User,
    WorkflowEvent,
    WorkflowInstance,
    WorkflowState,
)
from office_connect.core.org_units import ancestors_or_self, authorize_scoped, permission_holders
from office_connect.core.reference_numbers import allocate_reference_number
from office_connect.core.session import set_audit_context
from office_connect.core.time import MANILA, to_manila, to_utc, utc_now
from office_connect.core.workdays import add_working_days, load_nonworking_dates
from office_connect.core.workflow.steps import gate_steps
from office_connect.modules.reimbursement.models import (
    ReimbCashAdvance,
    ReimbClaim,
    ReimbConfig,
    ReimbReturnEvent,
    ReimbReturnReasonCatalog,
    ReimbStatusHistory,
)
from office_connect.modules.reimbursement.services import attachments as evidence
from office_connect.modules.reimbursement.services import cash_advance as ca
from office_connect.modules.reimbursement.services import checklist
from office_connect.modules.reimbursement.services import errors
from office_connect.modules.reimbursement.services import status as st
from office_connect.modules.reimbursement.services.compute import compute_claim_totals
from office_connect.modules.reimbursement.workflow import (
    FEATURE_FLAG_KEY,
    SUBJECT_KIND,
    definition_code,
)
from office_connect.core.money import to_money

_CLAIM_ACTIONS = frozenset({"approve", "return", "resubmit", "cancel"})
_JO_COS_STATUSES = frozenset({"job_order", "contract_of_service"})
#: claim kind → reference-number scope (core-service #5 mints ``XX-YYYY-NNNN``;
#: the counter row for a new scope is created on demand, so ``LQ`` needs no seed
#: and no migration). Numbers are never reused across either series.
REF_SCOPES: dict[str, str] = {
    st.REIMBURSEMENT_KIND: "RB",
    st.LIQUIDATION_KIND: "LQ",
}

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


async def owner_user(session: AsyncSession, claimant_id: int) -> User | None:
    """The claimant's live login account (``core_users.staff_id`` bridge).

    Public since R-6-clock: the liquidation reminder ladder needs the same
    staff→login bridge to address a cash advance's holder, and two functions
    resolving "who is this claimant, as a user" differently is precisely how a
    nudge ends up in the wrong inbox.
    """
    return (
        await session.execute(
            select(User).where(
                User.staff_id == claimant_id, User.is_active.is_(True)
            )
        )
    ).scalar_one_or_none()


async def is_claim_owner(
    session: AsyncSession, claim: ReimbClaim, actor_user_id: int
) -> bool:
    """Is this actor the claimant? Public because ``services/actions.py`` needs
    the same answer to synthesize a pre-instance action set (R-4-screens)."""
    actor = await session.get(User, actor_user_id)
    return bool(actor and actor.staff_id == claim.claimant_id)


async def _assert_advance_settled(session: AsyncSession, claim: ReimbClaim) -> None:
    """The money before the terminal state (R-6-liq-settle).

    ``settled`` is not merely the next rung — it ASSERTS that the cash advance
    is closed. Letting a bare ``approve`` assert it would leave a settled
    liquidation standing against an advance still holding its PD 1445 §89 slot,
    with no atomic way back. ``services/settlement.py::record_settlement``
    records the money and then drives this same approve inside one transaction,
    so the guard is already satisfied by the time it runs; anything else gets a
    409 naming the route that does the thing.

    Reads ``claim.status`` rather than re-reading the instance: the two are kept
    in lockstep by ``_sync_claim_from_event`` inside this module's transaction
    and the claim row is already locked, so a second engine read buys nothing.
    """
    if claim.cash_advance_id is None:
        raise errors.liquidation_without_advance()
    advance = (
        await session.execute(
            select(ReimbCashAdvance).where(
                ReimbCashAdvance.id == claim.cash_advance_id
            )
        )
    ).scalar_one_or_none()
    if advance is None or advance.status != ca.SETTLED:
        raise errors.settlement_required(claim_id=claim.id)


def _assert_payout_recorded(claim: ReimbClaim) -> None:
    """The evidence before the terminal state (R-7-events).

    ``paid_closed`` is not merely the last rung — it ASSERTS that FMS paid this
    claim. Spec §6.1 row 8 says so explicitly ("terminal (admin records payout
    ref)"), and until this increment a bare ``approve`` asserted it with nothing
    behind it: the claim went read-only carrying no reference, no date and no
    way to add either.

    ``services/external.py::record_payout`` writes the reference and then drives
    this same approve inside one transaction, so the guard is already satisfied
    by the time it runs; anything else gets a 409 naming the route that does the
    thing. The sibling of ``_assert_advance_settled``, and the same
    workflow-standards §12 rule.

    Synchronous — everything it needs is already on the locked claim row.
    """
    if not (claim.payout_ref or "").strip():
        raise errors.payout_required(claim_id=claim.id)


async def _assert_return_reasons(
    session: AsyncSession, reason_ids: Sequence[int]
) -> None:
    """≥1 reason, every one of them live and active (spec §5.6; delta row 44).

    Validated against the seeded taxonomy rather than trusted from the wire:
    ``reimb_return_events.reason_ids`` is append-only JSONB with no FK, so this
    is the only thing standing between the R-8 learning loop and junk ids."""
    if not reason_ids:
        raise errors.return_reason_required()
    wanted = list(dict.fromkeys(reason_ids))  # de-dupe, keep order
    live = set(
        (
            await session.execute(
                select(ReimbReturnReasonCatalog.id).where(
                    ReimbReturnReasonCatalog.id.in_(wanted),
                    ReimbReturnReasonCatalog.is_active.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )
    unknown = [i for i in wanted if i not in live]
    if unknown:
        raise errors.unknown_return_reason(unknown)


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
    vocab = st.vocabulary(claim.kind)
    if state.code in vocab.claimant:
        owner = await owner_user(session, claim.claimant_id)
        holder_id = owner.id if owner else instance.originator_user_id
        return ("user", holder_id)
    if state.code in vocab.external:
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
    claim.next_action = st.vocabulary(claim.kind).next_action.get(to_state.code)
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
    if not state.is_approval_gate or state.code in st.vocabulary(claim.kind).external:
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


async def create_draft_claim(
    session: AsyncSession,
    *,
    actor_user_id: int,
    kind: str = st.REIMBURSEMENT_KIND,
    now: datetime | None = None,
) -> ReimbClaim:
    """Create a draft claim for the actor's own staff record, stamping the
    §6.1 row-1 read-model at birth: status ``draft``, holder = the claimant's
    login, next action from that KIND's vocabulary — spec §7 rule 1 (one holder,
    always) holds from the first row, and My-Work's "waiting on you" includes
    drafts with no OR-branch. ``is_jo_cos`` derives from the directory
    employment status (spec §5.1). Business-field prefill belongs to
    ``services/drafts.py`` (and, for a liquidation, to
    ``services/liquidation.py``) — this function is only the status/holder
    writer. Flushes; the caller owns the commit.

    ``kind`` defaults to reimbursement so every pre-R-6-liq caller is unchanged;
    it is validated by the vocabulary lookup, which raises on an unknown kind
    rather than minting a claim no chain can run."""
    now = now or utc_now()
    st.vocabulary(kind)  # fail fast: an unknown kind has no chain and no labels
    set_audit_context(session, actor_id=actor_user_id)

    actor = await session.get(User, actor_user_id)
    staff = (
        await session.get(Staff, actor.staff_id)
        if actor is not None and actor.staff_id is not None
        else None
    )
    if staff is None or staff.deleted_at is not None:
        raise errors.no_staff_link()

    claim = ReimbClaim(
        kind=kind,
        claimant_id=staff.id,
        is_jo_cos=staff.employment_status in _JO_COS_STATUSES,
        status=st.DRAFT,
        holder_kind="user",
        holder_id=actor_user_id,
        holder_since=now,
        next_action=st.vocabulary(kind).next_action[st.DRAFT],
    )
    session.add(claim)
    await session.flush()
    session.add(
        ReimbStatusHistory(
            claim_id=claim.id,
            from_status=None,
            to_status=st.DRAFT,
            actor_id=actor_user_id,
        )
    )
    await session.flush()
    return claim


async def submit_claim(
    session: AsyncSession,
    *,
    claim_id: int,
    actor_user_id: int,
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
    # Routes on the claim's OWN kind (R-6-liq-chain): a liquidation submits onto
    # ``reimbursement.liquidation`` and burns an ``LQ-`` number, a reimbursement
    # onto ``reimbursement.claim`` and an ``RB-``. An unknown kind raises here
    # rather than starting an instance on a guessed chain.
    chain = definition_code(claim.kind)
    ref_scope = REF_SCOPES[claim.kind or st.REIMBURSEMENT_KIND]
    if claim.workflow_instance_id is not None:
        raise errors.claim_already_submitted()
    if not await is_claim_owner(session, claim, actor_user_id):
        raise errors.not_claim_owner()
    # Cancelled is terminal even pre-submit (no instance exists to make the
    # engine refuse) — without this, a cancelled draft would resurrect here and
    # burn a never-reused RB number. Checked under the row lock, so a
    # cancel↔submit race resolves to exactly one winner.
    if (claim.status or st.DRAFT) == st.CANCELLED:
        raise errors.claim_cancelled()

    staff = await session.get(Staff, claim.claimant_id)
    org_unit_id = staff.section_id or staff.division_id if staff else None
    if org_unit_id is None:
        raise errors.claimant_no_org_unit()

    # Totals read the persisted ``other_total`` column (0016) — the wizard's
    # money step wrote it via PATCH, and resubmit recomputes with it too.
    await compute_claim_totals(
        session, claim_id=claim.id, actor_user_id=actor_user_id
    )
    # A reimbursement that nets a cash advance (the R-6-liq-settle spawn) must
    # still be owed something. Edited below the advance it nets, ``settle``
    # returns a refund — and DV-32 would print "Amount refundable" on a payment
    # instrument, which is a liquidation's sentence on the wrong form.
    if (
        claim.kind == st.REIMBURSEMENT_KIND
        and claim.cash_advance_id is not None
        and to_money(claim.totals.get("to_refund") or 0) > 0
    ):
        raise errors.spawn_below_advance()
    # Documentary requirements (core-service #7, R-3). AFTER compute, because
    # the catalog rules read fresh totals; BEFORE start_instance, because an
    # incomplete packet must create no workflow instance and must never burn an
    # RB- number — the same ordering logic that already puts the flag gate here.
    await checklist.assert_packet_complete(
        session, claim=claim, actor_user_id=actor_user_id, now=now
    )
    # Flag gate fires inside start_instance — BEFORE a reference number is
    # burned (numbers are never reused, so order matters).
    instance = await wf.start_instance(
        session,
        definition_code=chain,
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
            session, scope=ref_scope, year=to_manila(now).year
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

    # The AUTHORITATIVE packet (R-5). Queued after commit, never rendered here:
    # WeasyPrint takes seconds and must never sit in a request path, and a
    # worker or renderer outage must not be able to fail a submit (spec §19.12 —
    # "claim saves anyway, generation queues, user sees a non-blocking notice").
    #
    # Placed AFTER ref_no allocation on purpose. A document generated before the
    # number exists is a draft; this pass is the one that prints RB-YYYY-NNNN on
    # the filed original and supersedes whatever the claimant previewed.
    generate_on_commit(session, evidence.HOLDER_KIND, claim.id)
    # A spawn burns its RB- number HERE, days after the liquidation that
    # produced it settled — and the liquidation's own Liquidation Report prints
    # that number ("claimed under reference RB-…"). Nothing else would ever
    # regenerate it, so the archived LR would say "not yet filed" forever and
    # the auditor would lose the trace between the two documents. One line, in
    # the one place that knows.
    if claim.spawned_from_claim_id is not None:
        generate_on_commit(
            session, evidence.HOLDER_KIND, claim.spawned_from_claim_id
        )
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
    belt on resubmit/cancel, the ≥1-reason rule, and the return-event record."""
    if action not in _CLAIM_ACTIONS:
        raise errors.unsupported_claim_action(action)
    now = now or utc_now()
    set_audit_context(session, actor_id=actor_user_id)

    claim = await _locked_claim(session, claim_id)
    if claim.workflow_instance_id is None:
        raise errors.claim_not_in_workflow()
    instance = await session.get(WorkflowInstance, claim.workflow_instance_id)

    if action == "return":
        # Spec §5.6: reason_ids is "≥1 mandatory", enforced HERE (the service
        # layer) so every caller is covered, not just the HTTP dialog.
        await _assert_return_reasons(session, reason_ids)

    if action in ("resubmit", "cancel"):
        # Belt to the engine's braces (FLAG 1): owner, or an admin reviewer.
        if not (
            await is_claim_owner(session, claim, actor_user_id)
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
        # A return is very often "you're missing a document", so resubmit gets
        # the same gate as submit — re-materialized, because the claimant has
        # been editing and the applicable set may have changed.
        await checklist.assert_packet_complete(
            session, claim=claim, actor_user_id=actor_user_id, now=now
        )
        instance.amount = to_money(claim.totals["grand"])
        await session.flush()

    if action == "approve":
        # Spec §9.4: an approver may approve past a FLAG, never past a missing
        # required item. Persisted rows only — see the service docstring for why
        # re-materializing mid-approval would violate "in-flight always
        # finishes" (workflow-standards §9).
        await checklist.assert_persisted_packet_complete(session, claim=claim)
        # Both chains end at a MONEY state, and the engine's approve carries no
        # payload — so on BOTH, the facts are recorded by a prior call in this
        # same transaction and the bare verb is refused here
        # (workflow-standards §12 rule 3). A liquidation must find its advance
        # settled (``services/settlement.py``, R-6-liq-settle); a reimbursement
        # must find its payment reference (``services/external.py``, R-7-events).
        if (claim.status or st.DRAFT) == st.HANDED_TO_FMS:
            if claim.kind == st.LIQUIDATION_KIND:
                await _assert_advance_settled(session, claim)
            else:
                _assert_payout_recorded(claim)

    key = idempotency_key or (
        f"{action}:{claim.id}:{instance.revision_no}"
        f":{instance.current_state_id}:{actor_user_id}"
    )
    # A replay returns the ORIGINAL event verbatim, so the side effects below
    # must not run twice: _sync_claim_from_event already no-ops (same state),
    # but the return-event insert would append a phantom second return.
    replayed = (
        await session.execute(
            select(WorkflowEvent.id).where(
                WorkflowEvent.instance_id == instance.id,
                WorkflowEvent.idempotency_key == key,
            )
        )
    ).first() is not None

    event = await wf.execute_action(
        session,
        instance_id=instance.id,
        action=action,
        actor_user_id=actor_user_id,
        comment=comment,
        idempotency_key=key,
        expected_version=expected_version,
        now=now,
    )

    if action == "return" and not replayed:
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

    if action == "resubmit" and not replayed:
        # Spec §10: "regeneration after any edit voids prior snapshots and
        # re-flags signature steps". The claimant has been fixing the claim, so
        # the packet that was approved-and-returned no longer describes it. The
        # generator is idempotent, so an unchanged document costs nothing; a
        # changed one supersedes its predecessor and the fresh chain (the engine
        # bumped revision_no) approves against the new copy.
        generate_on_commit(session, evidence.HOLDER_KIND, claim.id)
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
    if not await is_claim_owner(session, claim, actor_user_id):
        raise errors.not_claim_owner()
    if not comment:
        raise wf.errors.comment_required()
    # Idempotence belt: a double-cancel must not append a no-op
    # cancelled→cancelled row to the append-only history.
    if (claim.status or st.DRAFT) == st.CANCELLED:
        raise errors.claim_cancelled()

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
