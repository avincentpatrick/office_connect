"""Cash advances — the SINGLE sanctioned writer of ``reimb_cash_advances``.

The same chokepoint doctrine ``lifecycle.py`` applies to ``reimb_claims.status``
(workflow-standards §1: *"a status column mutated by scattered code is
forbidden"*), applied to the liquidation clock. Everything that can move
``status``, ``deadline_date`` or ``deadline_basis`` goes through this module, so
the three can never disagree with each other or with ``date_return``.

**Who records an advance** (R-6-clock kickoff decision): the Admin Officer /
Accounting, under the new ``reimb.cash_advance.manage`` permission. ``dv_no`` and
``dv_date`` are Accounting's own data — a claimant cannot know them — and the
PD 1445 §89 hard-block is only worth having if the record it guards is
authoritative. Claimants read their own advances; they do not write them.

**The deadline is pinned, not derived.** ``deadline_date`` is recomputed on
exactly one trigger — ``date_return`` moving — and never on a read. Two reasons,
one practical and one that matters more: the daily reminder sweep range-queries
the column instead of resolving the effective config pack per row; and the date a
traveller was *told* must not silently shift when an admin edits
``liquidation.deadline`` or a holiday lands in ``core_holidays``. This is exactly
the discipline R-5-gen arrived at the hard way with ``purpose`` — track which
question an edit actually answers, and recompute only what that answer changed.

Flushes, never commits: the caller owns the transaction (the module-wide contract
shared with ``compute_claim_totals``, ``allocate_reference_number`` and
``lifecycle.py``).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.money import to_money
from office_connect.core.session import set_audit_context
from office_connect.core.time import to_manila, utc_now
from office_connect.core.workdays import load_nonworking_dates
from office_connect.modules.reimbursement.models import (
    ReimbCashAdvance,
    ReimbClaim,
)
from office_connect.modules.reimbursement.services import deadline as dl
from office_connect.modules.reimbursement.services import errors
from office_connect.modules.reimbursement.services.checklist_facts import (
    effective_config,
)

#: CA statuses that still hold the §89 slot (the partial-unique index predicate).
#: ``overdue`` is deliberately among them: an advance does not stop blocking
#: because it went past its deadline — that is precisely when it blocks hardest.
UNLIQUIDATED_STATUSES: frozenset[str] = frozenset(
    {"open", "liquidation_started", "overdue"}
)

OPEN = "open"
LIQUIDATION_STARTED = "liquidation_started"
SETTLED = "settled"
OVERDUE = "overdue"

#: The COA warning copy (spec §4). Config, not a constant — see ``overdue_note``.
OVERDUE_NOTE_KEY = "liquidation.overdue_note"

#: Window handed to ``load_nonworking_dates`` on the working basis. Generously
#: covers the worst holiday clustering around n working days — the same
#: reasoning (and the same shape) as ``lifecycle._stamp_sla``.
_HOLIDAY_WINDOW_FACTOR = 4
_HOLIDAY_WINDOW_PAD = 14


# --------------------------------------------------------------------------
# Deadline resolution
# --------------------------------------------------------------------------


async def overdue_note(session: AsyncSession, *, today: date) -> str | None:
    """``liquidation.overdue_note`` — the COA consequence sentence, from config.

    One home for it, because two of them exist otherwise: the reminder ladder
    puts it in the D-0 body and the API puts it on the record the countdown ring
    renders. Two copies would drift, and this is text that must not.

    No code-side fallback on purpose. It states a legal consequence (6% interest,
    salary deduction) that the resident COA auditor owns; a developer's
    paraphrase standing in for a missing row would be indistinguishable from the
    real thing. A missing row therefore says nothing at all.
    """
    value = (await effective_config(session, today=today)).get(OVERDUE_NOTE_KEY)
    text = value.get("text") if isinstance(value, dict) else None
    return text if isinstance(text, str) and text else None


async def resolve_deadline(
    session: AsyncSession,
    *,
    date_return: date | None,
    today: date,
) -> tuple[date | None, str | None]:
    """``(deadline_date, deadline_basis)`` for a return date, as-of ``today``.

    Reads the effective config pack once and only touches ``core_holidays`` on
    the ``working`` basis — on the seeded ``calendar`` default this is pure
    arithmetic after a single config read.
    """
    if date_return is None:
        return (None, None)

    rule = dl.read_rule(await effective_config(session, today=today))
    nonworking: set[date] | None = None
    if rule.basis == dl.WORKING:
        nonworking = await load_nonworking_dates(
            session,
            date_return,
            date_return
            + timedelta(
                days=rule.days * _HOLIDAY_WINDOW_FACTOR + _HOLIDAY_WINDOW_PAD
            ),
        )
    computed = dl.liquidation_deadline(
        date_return=date_return, rule=rule, nonworking=nonworking
    )
    return (computed, rule.basis)


# --------------------------------------------------------------------------
# Lookups
# --------------------------------------------------------------------------


async def get_cash_advance(
    session: AsyncSession, cash_advance_id: int
) -> ReimbCashAdvance:
    row = (
        await session.execute(
            select(ReimbCashAdvance).where(ReimbCashAdvance.id == cash_advance_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise errors.cash_advance_not_found()
    return row


async def open_cash_advance_for(
    session: AsyncSession, claimant_id: int
) -> ReimbCashAdvance | None:
    """The claimant's one unliquidated advance, if any (the §89 slot holder)."""
    return (
        await session.execute(
            select(ReimbCashAdvance).where(
                ReimbCashAdvance.claimant_id == claimant_id,
                ReimbCashAdvance.status.in_(UNLIQUIDATED_STATUSES),
            )
        )
    ).scalars().first()


async def list_cash_advances(
    session: AsyncSession,
    *,
    claimant_id: int | None = None,
    statuses: frozenset[str] | None = None,
) -> list[ReimbCashAdvance]:
    """Advances, most-recently-issued first (NULL DV dates last)."""
    query = select(ReimbCashAdvance)
    if claimant_id is not None:
        query = query.where(ReimbCashAdvance.claimant_id == claimant_id)
    if statuses:
        query = query.where(ReimbCashAdvance.status.in_(statuses))
    query = query.order_by(
        ReimbCashAdvance.dv_date.desc().nullslast(), ReimbCashAdvance.id.desc()
    )
    return list((await session.execute(query)).scalars().all())


# --------------------------------------------------------------------------
# Writes
# --------------------------------------------------------------------------


def _validate(*, amount: Decimal, dv_date: date | None, date_return: date | None):
    if to_money(amount) <= Decimal("0.00"):
        raise errors.cash_advance_amount_invalid()
    if dv_date and date_return and date_return < dv_date:
        raise errors.cash_advance_dates_invalid()


async def _guard_section_89(session: AsyncSession, claimant_id: int) -> None:
    """Pre-flight the hard-block so the caller gets a sentence, not a 500.

    The DB index remains the actual guarantee — this check races, and is meant
    to. ``create_cash_advance`` still catches the ``IntegrityError`` behind it;
    losing the race yields the identical error, so the two paths are
    indistinguishable to a caller.
    """
    blocking = await open_cash_advance_for(session, claimant_id)
    if blocking is not None:
        raise errors.cash_advance_unliquidated(
            dv_no=blocking.dv_no, deadline=blocking.deadline_date
        )


async def create_cash_advance(
    session: AsyncSession,
    *,
    claimant_id: int,
    amount: Decimal,
    actor_user_id: int,
    dv_no: str | None = None,
    dv_date: date | None = None,
    dpo_no: str | None = None,
    date_return: date | None = None,
    now: datetime | None = None,
) -> ReimbCashAdvance:
    """Record a travel cash advance and pin its liquidation deadline."""
    now = now or utc_now()
    today = to_manila(now).date()
    set_audit_context(session, actor_id=actor_user_id)

    _validate(amount=amount, dv_date=dv_date, date_return=date_return)
    await _guard_section_89(session, claimant_id)

    deadline_date, deadline_basis = await resolve_deadline(
        session, date_return=date_return, today=today
    )
    row = ReimbCashAdvance(
        claimant_id=claimant_id,
        dv_no=dv_no,
        dv_date=dv_date,
        amount=to_money(amount),
        dpo_no=dpo_no,
        date_return=date_return,
        deadline_date=deadline_date,
        deadline_basis=deadline_basis,
        status=OPEN,
    )
    session.add(row)
    try:
        await session.flush()
    except IntegrityError as exc:
        # Lost the race against a concurrent create — the index caught it.
        # Re-raise as the same named 409 the pre-flight would have produced.
        if "uq_reimb_cash_advances_open_per_claimant" in str(exc.orig):
            raise errors.cash_advance_unliquidated(
                dv_no=None, deadline=None
            ) from exc
        raise
    return row


async def update_cash_advance(
    session: AsyncSession,
    *,
    cash_advance_id: int,
    actor_user_id: int,
    fields: dict,
    now: datetime | None = None,
) -> ReimbCashAdvance:
    """Edit an advance's recorded facts, recomputing the clock only if it moved.

    ``fields`` carries only the keys the caller actually sent (the API layer
    strips unset ones), so "cleared to NULL" and "not mentioned" stay distinct —
    the same convention ``drafts.update_draft_fields`` uses.
    """
    now = now or utc_now()
    today = to_manila(now).date()
    set_audit_context(session, actor_id=actor_user_id)

    row = await get_cash_advance(session, cash_advance_id)
    if row.status == SETTLED:
        # A settled advance is a closed financial record; reopening one is a
        # reversal with its own authority story, not a PATCH.
        raise errors.cash_advance_settled()

    writable = {"dv_no", "dv_date", "dpo_no", "amount", "date_return"}
    changes = {k: v for k, v in fields.items() if k in writable}

    amount = changes.get("amount", row.amount)
    dv_date = changes.get("dv_date", row.dv_date)
    date_return = changes.get("date_return", row.date_return)
    _validate(amount=amount, dv_date=dv_date, date_return=date_return)

    # THE question this edit might answer: did the clock's origin move?
    # Everything else is bookkeeping and must not disturb a pinned deadline.
    clock_moved = "date_return" in changes and changes["date_return"] != row.date_return

    for key, value in changes.items():
        setattr(row, key, to_money(value) if key == "amount" else value)

    if clock_moved:
        row.deadline_date, row.deadline_basis = await resolve_deadline(
            session, date_return=row.date_return, today=today
        )
        # A re-dated advance is a different promise: any overdue verdict was
        # about the OLD deadline, so let the sweep re-decide against the new one
        # rather than leaving a stale red badge on a claim that is now on track.
        if row.status == OVERDUE:
            row.status = OPEN

    await session.flush()
    return row


async def mark_overdue(
    session: AsyncSession,
    *,
    cash_advance: ReimbCashAdvance,
    actor_user_id: int | None = None,
) -> bool:
    """Flip an unliquidated advance past its deadline to ``overdue``.

    Spec §6.3 says *"Overdue is a derived badge, never a status"* — that governs
    the CLAIM, whose status is the workflow engine's to own. §5.4 gives the cash
    advance a real ``overdue`` enum value, because an unliquidated advance past
    30 days is a fact about a financial record that outlives any UI: COA asks
    for the count and the peso total (spec §13). Both hold at once — the CA
    stores it, the claim derives it.

    Returns True only when this call is what changed the row (idempotent).
    """
    if cash_advance.status not in (OPEN, LIQUIDATION_STARTED):
        return False
    set_audit_context(session, actor_id=actor_user_id)
    cash_advance.status = OVERDUE
    await session.flush()
    return True


async def mark_liquidation_started(
    session: AsyncSession,
    *,
    cash_advance: ReimbCashAdvance,
    actor_user_id: int | None = None,
) -> bool:
    """Called when a liquidation claim is filed against the advance (R-6-liq).

    Deliberately does NOT clear an ``overdue`` status: filing late does not
    un-late it, and the badge is what tells Accounting which settlements to
    chase. The §89 slot stays held either way.
    """
    if cash_advance.status != OPEN:
        return False
    set_audit_context(session, actor_id=actor_user_id)
    cash_advance.status = LIQUIDATION_STARTED
    await session.flush()
    return True


async def link_claim(
    session: AsyncSession,
    *,
    claim: ReimbClaim,
    cash_advance: ReimbCashAdvance,
    actor_user_id: int | None = None,
) -> None:
    """Point a claim at an advance and mirror the deadline onto it.

    ``reimb_claims.liquidation_deadline`` is a MIRROR, written here only, so the
    claim rail and the tracker render a countdown without joining. The advance
    remains the source of truth — ``update_cash_advance`` re-mirrors on every
    linked claim when the clock moves.
    """
    set_audit_context(session, actor_id=actor_user_id)
    claim.cash_advance_id = cash_advance.id
    claim.liquidation_deadline = cash_advance.deadline_date
    await session.flush()


async def remirror_deadline(
    session: AsyncSession, *, cash_advance: ReimbCashAdvance
) -> int:
    """Push a moved deadline onto every claim linked to this advance.

    Returns the number of claims updated. Called by the API layer after an edit
    that moved the clock — kept separate from ``update_cash_advance`` so the
    service stays a single-table writer and the fan-out is visible at its call
    site rather than hidden inside a PATCH.
    """
    claims = (
        (
            await session.execute(
                select(ReimbClaim).where(
                    ReimbClaim.cash_advance_id == cash_advance.id
                )
            )
        )
        .scalars()
        .all()
    )
    for claim in claims:
        claim.liquidation_deadline = cash_advance.deadline_date
    if claims:
        await session.flush()
    return len(claims)
