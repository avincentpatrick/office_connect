"""The FMS journey — relaying what FMS says, and recording what FMS finally did.

Everything up to ``handed_to_fms`` is the platform's. After that the packet is
physically with the Financial Management Service, and the platform's job shrinks
to three things: keep the claim findable (R-7-queue), relay what FMS says, and
record what FMS finally did. This module is the last two.

**The relay is a PURE APPEND, and the sub-status does not move the claim.** That
is delta row 38's decision, and it is the reason ``reimb_external_events`` exists
as a table at all: spec §6.1 row 6 shows *With Budget → With Accounting →
Payment Processing (admin, **any order/skips allowed**)*, and the engine's closed
action enum routes one ``(state, action)`` pair by guards, not by user choice —
multi-way user-chosen branching cannot be authored. So the whole external leg
rides ONE ``handed_to_fms`` state, and the sub-statuses ride the event table over
it.

That constraint turns out to describe reality better than states would have. A
sub-status is *news about someone else's process*, not a position in ours: FMS
can go straight from Budget to payment, can bounce a packet back to Budget, and
can tell you twice in a week that it is still with Accounting. Membership in the
closed set is enforced; **order never is** — the R-9 QA line is literally
"Statuses skip/reorder legally", and a repeat is legal too.

**Both claim kinds.** A liquidation sits at ``handed_to_fms`` exactly as a
reimbursement does, and is exactly as invisible while it does. Delta row 116's
liquidation exclusion is about ``fms_returned`` — a STATE, which would need a
screen and a transition — not about a relay that adds no state and reuses one
dialog. FMS handles both packets through the same three desks.

**``mark_paid`` is workflow-standards §12's second instance.** The engine's
``approve`` carries no payload, so a transition whose meaning depends on a
reference number is two calls in one transaction: record the payout, then drive
the unchanged verb. ``services/settlement.py`` established the shape on the
liquidation chain; this is the reimbursement chain's half, and the three rules
are the same three — one transaction, the data write first (so the CAS token the
client read is still the token at transition time), and a chokepoint that refuses
the bare verb while NAMING the route that does the thing.

Flushes, never commits — the module-wide contract.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.session import set_audit_context
from office_connect.core.time import to_manila, utc_now
from office_connect.modules.reimbursement.models import (
    ReimbClaim,
    ReimbExternalEvent,
)
from office_connect.modules.reimbursement.services import attachments as evidence
from office_connect.modules.reimbursement.services import errors
from office_connect.modules.reimbursement.services import lifecycle
from office_connect.modules.reimbursement.services import notify
from office_connect.modules.reimbursement.services import status as st

# --- The closed set (spec §6.1 row 6) ---------------------------------------

WITH_BUDGET = "with_budget"
WITH_ACCOUNTING = "with_accounting"
PAYMENT_PROCESSING = "payment_processing"

#: Written ONLY by :func:`record_payout`, never accepted from the relay. It is
#: not a sub-status — it is the terminal, and it rides the event table only so
#: the tracker's FMS chronology has an ending instead of stopping mid-journey.
PAID = "paid"

#: What an Admin Officer may relay. Membership is enforced; ORDER never is.
RELAY_STATUSES: tuple[str, ...] = (
    WITH_BUDGET,
    WITH_ACCOUNTING,
    PAYMENT_PROCESSING,
)

#: Display strings, here for the same reason ``status.py`` holds the state
#: labels: the UI renders labels, never raw codes, and one vocabulary means the
#: notification, the tracker, the claim rail and the queue row cannot disagree
#: about what ``with_accounting`` is called.
LABELS: dict[str, str] = {
    WITH_BUDGET: "With Budget",
    WITH_ACCOUNTING: "With Accounting",
    PAYMENT_PROCESSING: "Payment processing",
    PAID: "Paid",
}


def label(status: str) -> str:
    """A sub-status in the claimant's language, falling back to the raw code."""
    return LABELS.get(status, status)


# --- Reads ------------------------------------------------------------------


async def claim_events(
    session: AsyncSession, claim_id: int
) -> list[ReimbExternalEvent]:
    """Every FMS event on a claim, oldest first — the tracker's second lane."""
    return list(
        (
            await session.execute(
                select(ReimbExternalEvent)
                .where(ReimbExternalEvent.claim_id == claim_id)
                .order_by(ReimbExternalEvent.id)
            )
        )
        .scalars()
        .all()
    )


async def latest_event(
    session: AsyncSession, claim_id: int
) -> ReimbExternalEvent | None:
    """The most recent FMS event on one claim (the claim rail's single row)."""
    return (
        await session.execute(
            select(ReimbExternalEvent)
            .where(ReimbExternalEvent.claim_id == claim_id)
            .order_by(ReimbExternalEvent.id.desc())
            .limit(1)
        )
    ).scalars().first()


async def latest_events(
    session: AsyncSession, claim_ids: list[int]
) -> dict[int, ReimbExternalEvent]:
    """``{claim_id: newest event}`` for a whole page, in ONE query.

    ``DISTINCT ON`` rather than a correlated subquery per row: the queue renders
    up to ``MAX_LIMIT`` rows and a query per row is the same unbounded-fan-out
    mistake ``descendants_or_self`` was built to avoid. Covered by
    ``ix_reimb_external_events_claim_id``.
    """
    if not claim_ids:
        return {}
    rows = (
        (
            await session.execute(
                select(ReimbExternalEvent)
                .where(ReimbExternalEvent.claim_id.in_(claim_ids))
                .distinct(ReimbExternalEvent.claim_id)
                .order_by(
                    ReimbExternalEvent.claim_id, ReimbExternalEvent.id.desc()
                )
            )
        )
        .scalars()
        .all()
    )
    return {row.claim_id: row for row in rows}


# --- The relay --------------------------------------------------------------


def _assert_not_future(event_date: date | None, *, now: datetime) -> None:
    """FMS cannot have done something tomorrow. Manila, because the operator is
    typing a Philippine calendar date off a Philippine desk."""
    if event_date is not None and event_date > to_manila(now).date():
        raise errors.external_event_future_date()


async def record_external_event(
    session: AsyncSession,
    *,
    claim_id: int,
    status: str,
    actor_user_id: int,
    noted_by: str | None = None,
    note: str | None = None,
    event_date: date | None = None,
    now: datetime | None = None,
    _allow_terminal: bool = False,
) -> ReimbExternalEvent:
    """Append one FMS journey update. Moves NOTHING.

    Spec §3.2 puts "Set external FMS statuses" with the Admin Officer and the
    System Admin; the route enforces that. This layer enforces what is true of
    the RECORD: the claim is with FMS, the status is one the platform knows, and
    the date is not in the future.

    The claim row is read WITHOUT a lock, deliberately. Nothing here mutates it,
    so there is no lost update to serialize; the only race is a concurrent
    transition landing between the state check and the insert, which produces a
    relay recorded a second after the hand-back. That is noise in an append-only
    log, not corruption — and taking the claim lock here would put a pure read
    path into the same lock order as every transition for no gain.

    ``_allow_terminal`` is the private door :func:`record_payout` comes through
    to write the ``paid`` row. It is not a parameter any route passes: the whole
    point of the closed relay set is that closing a claim cannot be done by
    typing a status into the relay dialog.
    """
    now = now or utc_now()
    set_audit_context(session, actor_id=actor_user_id)

    if status == PAID and not _allow_terminal:
        raise errors.external_status_is_terminal()
    if status not in RELAY_STATUSES and not (
        status == PAID and _allow_terminal
    ):
        raise errors.unknown_external_status(status, sorted(RELAY_STATUSES))
    _assert_not_future(event_date, now=now)

    claim = (
        await session.execute(select(ReimbClaim).where(ReimbClaim.id == claim_id))
    ).scalar_one_or_none()
    if claim is None:
        raise errors.claim_not_found()
    if (claim.status or st.DRAFT) != st.HANDED_TO_FMS:
        raise errors.external_event_wrong_state(
            status=st.vocabulary(claim.kind).labels.get(
                claim.status or st.DRAFT, claim.status or st.DRAFT
            )
        )

    # What FMS said LAST, read before the insert — it decides whether the
    # claimant hears about this one (see below).
    previous = await latest_event(session, claim.id)

    event = ReimbExternalEvent(
        claim_id=claim.id,
        status=status,
        noted_by=(noted_by or "").strip() or None,
        note=(note or "").strip() or None,
        event_date=event_date,
        created_by=actor_user_id,
    )
    # INSERT only, never ``session.merge``: the table carries no ``updated_*``
    # columns (tests/test_migrations.py pins that shape) and UPDATE/DELETE are
    # revoked from ``oc_app`` in migration 0013 (tests/test_append_only.py).
    session.add(event)
    await session.flush()

    # Spec §12: "External status updated → Claimant: 'Your claim is now With
    # Accounting'". Two cases send nothing, for the same underlying reason —
    # a notification that adds no information trains people to ignore the ones
    # that do.
    #
    #  1. A relay that REPEATS the previous status. That sentence is a claim
    #     about change, and saying it twice is not news. Re-entry after a
    #     DIFFERENT status does notify, because that genuinely is.
    #  2. The terminal ``paid`` row. Spec §12 gives "Paid / Settled" its own
    #     message, and ``record_payout`` sends it — with the payment reference
    #     and the amount on it, which "your claim is now Paid" would not have.
    #     Both firing sends a traveller two notifications about one payment, the
    #     less informative one first. (Caught in the R-7-events live smoke, not
    #     by any assertion: both messages were individually correct.)
    changed = previous is None or previous.status != status
    if changed and status != PAID:
        await notify.notify_external_status(session, claim=claim, event=event)
    return event


# --- The terminal: what FMS finally did -------------------------------------


async def record_payout(
    session: AsyncSession,
    *,
    claim_id: int,
    actor_user_id: int,
    payout_ref: str | None,
    paid_on: date | None,
    comment: str | None = None,
    expected_version: int | None = None,
    now: datetime | None = None,
) -> ReimbClaim:
    """Record what FMS paid, and close the claim — one transaction.

    Spec §6.1 row 8: ``Paid / Closed`` is "terminal (admin records payout ref)".
    Until R-7-events it was a bare ``approve`` that recorded nothing, which is
    the failure workflow-standards §12 exists to prevent — and the ordering here
    is that standard's three rules, in order:

    1. **One transaction.** The reference, the ``paid`` event, the transition,
       the retention clock and the notification commit together or not at all.
       Split in two, a payout recorded without its approve would leave a claim
       carrying a payment reference while still sitting in the queue as work
       outstanding, and there is no compensating transaction in this codebase.
    2. **The data write goes FIRST**, and touches ``reimb_claims`` only — never
       ``instance.row_version``, which ``execute_action`` owns. So the CAS token
       the client read is still the token at transition time; reversed, a stale
       ``expected_version`` could file a payment reference against a transition
       the engine then refused.
    3. **The gate refuses the bare verb.** ``lifecycle._assert_payout_recorded``
       is already satisfied by the time the approve below runs; anything else
       gets a 409 naming this route.

    ``payout_ref`` is required (user-confirmed at kickoff). A terminal state that
    asserts nothing is the bare approve this call replaces, ``paid_closed`` is
    read-only afterwards, and there is no amendment route — so the refusal points
    at the relay instead: an Admin Officer without a reference yet has something
    honest to record, which is *Payment processing*.
    """
    now = now or utc_now()
    set_audit_context(session, actor_id=actor_user_id)

    claim = await lifecycle._locked_claim(session, claim_id)
    if claim.kind != st.REIMBURSEMENT_KIND:
        # A liquidation's terminal is ``settled``, and it records a refund
        # receipt rather than a payout — a different act, on its own route.
        raise errors.payout_not_a_reimbursement()

    # Every refusal fires before any write.
    if claim.payout_ref is not None:
        raise errors.payout_already_recorded(
            payout_ref=claim.payout_ref, paid_on=claim.paid_on
        )
    if (claim.status or st.DRAFT) != st.HANDED_TO_FMS:
        raise errors.payout_wrong_state(
            status=st.vocabulary(claim.kind).labels.get(
                claim.status or st.DRAFT, claim.status or st.DRAFT
            )
        )
    reference = (payout_ref or "").strip()
    if not reference:
        raise errors.payout_ref_required()
    if paid_on is None:
        raise errors.payout_date_required()
    _assert_not_future(paid_on, now=now)

    claim.payout_ref = reference
    claim.paid_on = paid_on
    claim.paid_by = actor_user_id
    await session.flush()

    # The FMS chronology gets its ending. Without it the tracker's external lane
    # stops at "Payment processing" and the reader has to infer the rest from a
    # status row in the other lane.
    await record_external_event(
        session,
        claim_id=claim.id,
        status=PAID,
        actor_user_id=actor_user_id,
        note=note_for_payout(reference),
        event_date=paid_on,
        now=now,
        _allow_terminal=True,
    )

    claim = await lifecycle.claim_action(
        session,
        claim_id=claim.id,
        action="approve",
        actor_user_id=actor_user_id,
        comment=comment,
        expected_version=expected_version,
        now=now,
    )
    # The GRDS clock starts HERE, on the whole file, and this is the first time
    # in the platform's life that it ever has (services/attachments.py has been
    # promising "R-7" since R-2). AFTER the approve on purpose: the clock runs
    # from final settlement, and until the transition lands the claim is not
    # final.
    await evidence.start_retention_clock(session, claim_id=claim.id, now=now)
    await notify.notify_paid(session, claim=claim)
    return claim


def note_for_payout(payout_ref: str) -> str:
    """The ``paid`` event's note. One sentence, and it carries the reference —
    the event table is what the tracker renders, and a "Paid" row that does not
    say what it was paid against sends the reader back to the claim header."""
    return f"Payment reference {payout_ref}."
