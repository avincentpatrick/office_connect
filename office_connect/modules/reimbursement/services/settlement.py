"""Settling a liquidation — spec §6.2's two side-steps (R-6-liq-settle).

R-6-clock built the *question* (a pinned COA 30-day deadline on an advance),
R-6-liq-chain built the *chain* that answers it. This module is the answer's
CONTENT: what was advanced, what was actually spent, and which of two things
closes the gap — a refund evidenced by a DOH official receipt, or a difference
still owed the traveller.

**Recording the money and closing the claim are ONE act.** The engine's
``approve`` carries no payload (``wf.execute_action`` takes an actor, a comment
and a CAS token — nothing else), so a settlement cannot ride on it without
forking ``execute_action``. The alternative — record now, approve later — was
rejected on a concrete failure: ``mark_settled`` releases the PD 1445 §89 slot
the instant it commits, so a settlement whose approve never followed would let
the traveller take a NEW advance while a live liquidation still stood against
the old one, and migration ``0020``'s belt index then forbids repairing it.
There is no compensating transaction anywhere in this codebase. Folded into one
service call inside one transaction, every failure rolls back together.

That is the general rule this increment establishes, and it is written down in
workflow-standards: **a decision that must record data is a separate, prior
service call in the same transaction — never a widened engine verb.**

**Nothing here trusts a client figure.** ``to_reimburse`` and ``to_refund`` are
read from the claim's server-computed ``totals`` snapshot, which
``per_diem.settle`` produced. A caller may ECHO the refund back so a stale
screen is caught before it records the wrong receipt against the wrong amount;
it may never propose one (standing prohibition: no client-side money math).

**Lock order is advance → claim**, matching ``liquidation.start_liquidation`` —
the only other path that touches both rows. Nothing anywhere locks claim →
advance (``compute`` and ``checklist_facts`` read it with a plain SELECT), so
the pair cannot deadlock.

Flushes, never commits — the module-wide contract.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.documents import generate_on_commit
from office_connect.core.models import User
from office_connect.core.money import money_str, to_money
from office_connect.core.session import set_audit_context
from office_connect.core.time import utc_now
from office_connect.modules.reimbursement.models import (
    ReimbCashAdvance,
    ReimbClaim,
    ReimbItineraryLeg,
)
from office_connect.modules.reimbursement.services import attachments as evidence
from office_connect.modules.reimbursement.services import cash_advance as ca
from office_connect.modules.reimbursement.services import errors
from office_connect.modules.reimbursement.services import lifecycle
from office_connect.modules.reimbursement.services import notify
from office_connect.modules.reimbursement.services import status as st
from office_connect.modules.reimbursement.services.compute import compute_claim_totals

_ZERO = Decimal("0.00")

#: A spawn that still occupies the liquidation's one "Reimbursement Due" slot.
#: ``cancelled`` is excluded so a mistaken spawn can be cancelled and re-taken —
#: the same exclusion, for the same reason, as ``liquidation.LIVE_STATUSES``.
LIVE_SPAWN_STATUSES: frozenset[str] = frozenset(
    st.REIMBURSEMENT.all_states
) - {st.CANCELLED}

#: The leg columns a traveller supplies. The computed three
#: (``per_diem_pct``/``per_diem_amount``/``leg_total``) are deliberately absent:
#: ``compute_claim_totals`` rewrites them on the spawn, and copying a stale
#: figure across would let the two claims' arithmetic disagree.
_LEG_INPUTS = (
    "leg_date",
    "place",
    "destination_region_code",
    "time_depart",
    "time_arrive",
    "transport_mode",
    "fare",
    "lodging_provided",
    "meals_provided",
)

#: The trip the liquidation described. The spawn is the SAME trip claimed a
#: second way, so every one of these carries over verbatim — anything the
#: traveller had to retype would be a chance to describe a different journey
#: than the one the advance funded (``start_liquidation``'s argument for
#: prefilling ``date_return``, one level out).
_TRIP_FIELDS = (
    "activity_id",
    "dpo_no",
    "dpo_date",
    "dpo_document_id",
    "purpose",
    "destination",
    "destination_region_code",
    "date_depart",
    "date_return",
    "is_within_50km",
    "overnight_stay",
    "fund_source",
    "other_total",
)


# --------------------------------------------------------------------------
# Reads
# --------------------------------------------------------------------------


def settlement_mode(totals: dict) -> str:
    """Which branch of spec §6.2 this liquidation's money takes.

    Derived from the figures ``per_diem.settle`` already produced rather than
    recomputed from ``grand``/``advance`` — a second subtraction here would be a
    second implementation of settlement, free to drift from the first.
    """
    if to_money(totals.get("to_refund") or _ZERO) > _ZERO:
        return ca.REFUND
    if to_money(totals.get("to_reimburse") or _ZERO) > _ZERO:
        return ca.OVER_ADVANCE
    return ca.EXACT


async def spawn_for_liquidation(
    session: AsyncSession, liquidation_claim_id: int
) -> ReimbClaim | None:
    """The live "Reimbursement Due" claim spawned from this liquidation, if any."""
    return (
        await session.execute(
            select(ReimbClaim)
            .where(
                ReimbClaim.spawned_from_claim_id == liquidation_claim_id,
                ReimbClaim.status.in_(LIVE_SPAWN_STATUSES),
            )
            .order_by(ReimbClaim.id)
        )
    ).scalars().first()


# --------------------------------------------------------------------------
# Recording the settlement
# --------------------------------------------------------------------------


def _validate_receipt(
    *,
    mode: str,
    to_refund: Decimal,
    or_no: str | None,
    or_date: date | None,
    refund_amount: Decimal | None,
) -> None:
    """The receipt must match the branch the money actually took.

    COA's rule is that an excess cash advance is refunded and *evidenced by an
    official receipt*; the OR number and date are what an auditor traces from
    the Liquidation Report into the books (research digest, round 1). So a
    refund without one is refused — and an OR on a settlement where nothing was
    refunded is refused just as hard, because that is a receipt for a payment
    that never happened.
    """
    supplied = bool(or_no) or or_date is not None
    if mode == ca.REFUND:
        if not or_no or or_date is None:
            raise errors.refund_receipt_required(amount=money_str(to_refund))
    elif supplied:
        raise errors.refund_receipt_not_applicable()

    if refund_amount is None:
        return
    expected = to_refund if mode == ca.REFUND else _ZERO
    if to_money(refund_amount) != expected:
        raise errors.refund_amount_mismatch(
            expected=money_str(expected), given=money_str(refund_amount)
        )


async def record_settlement(
    session: AsyncSession,
    *,
    claim_id: int,
    actor_user_id: int,
    or_no: str | None = None,
    or_date: date | None = None,
    refund_amount: Decimal | None = None,
    comment: str | None = None,
    expected_version: int | None = None,
    now: datetime | None = None,
) -> ReimbClaim:
    """Record how a liquidation settled, and close it — one transaction.

    Spec §3.2 puts "Record settlement (refund OR / payout)" with the Admin
    Officer and the System Admin; the route enforces that, and the engine's own
    ``resolve_authority`` remains the authorization of record for the transition
    this call then drives.
    """
    now = now or utc_now()
    set_audit_context(session, actor_id=actor_user_id)

    # Read unlocked first, only to learn which advance to lock. Everything that
    # decides anything is re-read under the locks below.
    claim = (
        await session.execute(select(ReimbClaim).where(ReimbClaim.id == claim_id))
    ).scalar_one_or_none()
    if claim is None:
        raise errors.claim_not_found()
    if claim.kind != st.LIQUIDATION_KIND:
        raise errors.not_a_liquidation()
    if claim.cash_advance_id is None:
        raise errors.liquidation_without_advance()

    advance = (
        await session.execute(
            select(ReimbCashAdvance)
            .where(ReimbCashAdvance.id == claim.cash_advance_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if advance is None:
        raise errors.cash_advance_not_found()
    claim = await lifecycle._locked_claim(session, claim_id)
    if claim.cash_advance_id != advance.id:
        # The link moved between the two reads. Nothing in the module does this
        # today (``link_claim`` runs once, at ``start_liquidation``), but a
        # settlement recorded against an advance the claim no longer points at
        # would be the worst possible way to find that out.
        raise errors.liquidation_without_advance()

    # Every refusal fires before any write.
    if advance.status == ca.SETTLED:
        raise errors.settlement_already_recorded(
            or_no=advance.refund_or_no,
            settled_at=advance.settled_at.date() if advance.settled_at else None,
        )
    status = claim.status or st.DRAFT
    if status != st.HANDED_TO_FMS:
        raise errors.settlement_wrong_state(status=status)
    totals = claim.totals or {}
    if not totals.get("grand"):
        raise errors.settlement_totals_missing()

    to_refund = to_money(totals.get("to_refund") or _ZERO)
    mode = settlement_mode(totals)
    _validate_receipt(
        mode=mode,
        to_refund=to_refund,
        or_no=or_no,
        or_date=or_date,
        refund_amount=refund_amount,
    )

    await ca.mark_settled(
        session,
        cash_advance=advance,
        actor_user_id=actor_user_id,
        mode=mode,
        refund_amount=to_refund if mode == ca.REFUND else None,
        or_no=or_no if mode == ca.REFUND else None,
        or_date=or_date if mode == ca.REFUND else None,
        now=now,
    )
    # AFTER the advance write, never before: ``mark_settled`` never touches
    # ``instance.row_version``, so the CAS token the client read is still the
    # token at approve time. Reversed, a caller could pass a stale version and
    # have the money recorded against a claim the approve then refused.
    claim = await lifecycle.claim_action(
        session,
        claim_id=claim.id,
        action="approve",
        actor_user_id=actor_user_id,
        comment=comment,
        expected_version=expected_version,
        now=now,
    )
    # The Liquidation Report prints the OR number, and until now it could not:
    # the submit-time copy was produced before the refund existed. Queued after
    # commit like every other generation pass, and idempotent — the fingerprint
    # check means an exact-match settlement that changed no printed fact
    # re-renders nothing.
    generate_on_commit(session, evidence.HOLDER_KIND, claim.id)
    # The GRDS clock (R-7-events). ``settled`` is the liquidation chain's final
    # settlement in the literal GRDS-2023 sense, so it starts the same 10-year
    # period ``paid_closed`` does on a reimbursement. AFTER the approve: until
    # the transition lands, the record is not final.
    await evidence.start_retention_clock(session, claim_id=claim.id, now=now)
    # Recording the settlement is the Admin Officer's act; claiming an
    # over-advance is the traveller's. Without this the two never meet.
    await notify.notify_settlement(session, claim=claim, advance=advance)
    return claim


# --------------------------------------------------------------------------
# The "Reimbursement Due" spawn
# --------------------------------------------------------------------------


async def spawn_reimbursement(
    session: AsyncSession,
    *,
    liquidation_claim_id: int,
    actor_user_id: int,
    now: datetime | None = None,
) -> ReimbClaim:
    """Spec §6.2's over-advance side-step: "one tap, pre-filled".

    The spawn is the SAME trip claimed a second way, so it carries the same trip
    header, the same itinerary, and — this is the load-bearing part — a link to
    the same cash advance. That link is what makes ``compute_claim_totals`` net
    ``grand − advance`` and DV-32 print the standard GAM shape (*Total claim /
    Less: cash advance / Amount due the payee*). Parking the bare difference in
    ``other_total`` instead would have printed a fabricated expense category and
    an empty itinerary for a trip that demonstrably happened.

    The link is written DIRECTLY rather than through ``cash_advance.link_claim``:
    that function also mirrors ``deadline_date`` onto the claim, and a
    reimbursement answers no liquidation clock — a countdown ring on this claim
    would be counting down to nothing. ``remirror_deadline`` is kind-filtered for
    the same reason.

    **Owner-only.** The traveller is the maker of their own claim, exactly as
    they are of the liquidation (delta row 43's reasoning, twice applied).
    Settlement is the Admin Officer's act; claiming what you are owed is yours.

    Evidence carry-over (the ``TO-01``/``CTC-47`` the traveller already attached
    to the liquidation) is a RECORDED DEFERRAL, not an oversight: re-using an
    attachment join across two claims raises a provenance question — whose
    evidence is it, and what happens when one claim is cancelled — that is worth
    answering once, generally, rather than inventing here. The spawn is a
    pre-filled draft; the wizard finishes it.
    """
    now = now or utc_now()
    set_audit_context(session, actor_id=actor_user_id)

    source = await lifecycle._locked_claim(session, liquidation_claim_id)
    if source.kind != st.LIQUIDATION_KIND:
        raise errors.not_a_liquidation()

    actor = await session.get(User, actor_user_id)
    if actor is None or actor.staff_id != source.claimant_id:
        raise errors.not_advance_holder()

    advance = (
        await session.get(ReimbCashAdvance, source.cash_advance_id)
        if source.cash_advance_id is not None
        else None
    )
    if advance is None:
        raise errors.liquidation_without_advance()
    if advance.settlement_mode != ca.OVER_ADVANCE:
        raise errors.spawn_not_over_advance(mode=advance.settlement_mode)

    existing = await spawn_for_liquidation(session, source.id)
    if existing is not None:
        raise errors.spawn_exists(claim_id=existing.id, ref_no=existing.ref_no)

    claim = await lifecycle.create_draft_claim(
        session,
        actor_user_id=actor_user_id,
        kind=st.REIMBURSEMENT_KIND,
        now=now,
    )
    for field in _TRIP_FIELDS:
        setattr(claim, field, getattr(source, field))
    claim.cash_advance_id = advance.id
    claim.spawned_from_claim_id = source.id

    legs = (
        (
            await session.execute(
                select(ReimbItineraryLeg)
                .where(
                    ReimbItineraryLeg.claim_id == source.id,
                    ReimbItineraryLeg.deleted_at.is_(None),
                )
                .order_by(ReimbItineraryLeg.seq, ReimbItineraryLeg.id)
            )
        )
        .scalars()
        .all()
    )
    for seq, leg in enumerate(legs, start=1):
        session.add(
            ReimbItineraryLeg(
                claim_id=claim.id,
                seq=seq,
                **{field: getattr(leg, field) for field in _LEG_INPUTS},
            )
        )

    try:
        await session.flush()
    except IntegrityError as exc:
        # Lost the race against a concurrent tap — the 0020 index caught it.
        # Re-raise as the same named 409 the pre-flight would have produced
        # (the ``create_cash_advance`` precedent for a belt-caught duplicate).
        if "uq_reimb_claims_spawn_per_liquidation" in str(exc.orig):
            raise errors.spawn_exists(claim_id=None, ref_no=None) from exc
        raise

    await compute_claim_totals(
        session, claim_id=claim.id, actor_user_id=actor_user_id
    )
    return claim
