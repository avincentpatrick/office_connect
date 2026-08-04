"""Starting a liquidation against a cash advance (R-6-liq-chain).

R-6-clock built the *question* — an advance with a pinned COA 30-day deadline, a
countdown and a reminder ladder. This module is where the traveller *answers* it:
one call turns "you hold an unliquidated advance" into a draft liquidation claim,
linked to the advance and already on its clock.

**A liquidation is a `reimb_claims` row, not a new table.** Same schema, same
wizard, same checklist engine; what differs is ``kind``, and everything that
reads ``kind`` — the catalog rows, the template bindings, the status vocabulary,
the workflow definition — is already data. So this module composes existing
services and owns no storage of its own:

- ``lifecycle.create_draft_claim(kind="liquidation")`` writes the status/holder
  read-model (it stays the only writer of ``reimb_claims.status``);
- ``cash_advance.link_claim`` points the claim at the advance and mirrors the
  deadline (it stays the only writer of ``reimb_cash_advances``);
- ``cash_advance.mark_liquidation_started`` moves the advance's own status.

Flushes, never commits — the module-wide contract, and what makes starting a
liquidation atomic: the draft, the link, the deadline mirror and the advance's
status move together or not at all.

**Owner-only** (v1). Filing the liquidation IS certification A, and A certifies
that the *claimant* incurred the expenses — an Admin Officer filing on their
behalf would put the wrong name against a COA certification. This is the same
reasoning that keeps ``submit_claim`` owner-only (delta row 43), and it is a
recorded deferral rather than an oversight: an assisted-filing path needs the
maker/checker question answered first.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.models import User
from office_connect.core.session import set_audit_context
from office_connect.core.time import utc_now
from office_connect.modules.reimbursement.models import ReimbCashAdvance, ReimbClaim
from office_connect.modules.reimbursement.services import cash_advance as ca
from office_connect.modules.reimbursement.services import errors
from office_connect.modules.reimbursement.services import lifecycle
from office_connect.modules.reimbursement.services import status as st

#: A liquidation that still occupies the advance's one slot. ``cancelled`` is
#: excluded so a mistaken start can be cancelled and re-filed; every other
#: state — including ``settled`` — counts, because a settled advance already has
#: its answer and a second liquidation would be a second answer to one question.
LIVE_STATUSES: frozenset[str] = frozenset(st.LIQUIDATION.all_states) - {st.CANCELLED}


async def liquidation_for_advance(
    session: AsyncSession, cash_advance_id: int
) -> ReimbClaim | None:
    """The advance's live liquidation claim, if one has been started."""
    return (
        await session.execute(
            select(ReimbClaim)
            .where(
                ReimbClaim.cash_advance_id == cash_advance_id,
                ReimbClaim.kind == st.LIQUIDATION_KIND,
                ReimbClaim.status.in_(LIVE_STATUSES),
            )
            .order_by(ReimbClaim.id)
        )
    ).scalars().first()


async def start_liquidation(
    session: AsyncSession,
    *,
    cash_advance_id: int,
    actor_user_id: int,
    now: datetime | None = None,
) -> ReimbClaim:
    """Open a draft liquidation against ``cash_advance_id``.

    Prefills what the advance already knows — ``dpo_no`` and the trip's return
    date — so the traveller starts on the Trip step with the fields Accounting
    filled in rather than re-typing a DV they never saw. Everything else is
    theirs to enter through the normal wizard.

    The advance row is locked ``FOR UPDATE`` for the whole call, which is what
    makes the one-live-liquidation rule hold under a double-tap: two concurrent
    requests serialize on the lock and the second sees the first's claim. The
    lock order is advance → claim, and no other path locks the two together, so
    this cannot deadlock against ``lifecycle._locked_claim``.

    ``uq_reimb_claims_live_liquidation_per_advance`` (migration ``0020``) is the
    DB belt behind this service lock — the same order the claim↔instance
    uniqueness took (service lock at R-4-app, index at ``0015``). Its predicate
    is deliberately WIDER than ``LIVE_STATUSES``: the index uses ``status IS
    DISTINCT FROM 'cancelled'``, which includes an un-stamped NULL status, while
    the service check uses ``IN (live states)``, which does not. The gap is
    caught below and re-raised as the same named 409 the pre-flight produces, so
    the two paths stay indistinguishable to a caller.
    """
    now = now or utc_now()
    set_audit_context(session, actor_id=actor_user_id)

    advance = (
        await session.execute(
            select(ReimbCashAdvance)
            .where(ReimbCashAdvance.id == cash_advance_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if advance is None:
        raise errors.cash_advance_not_found()
    if advance.status == ca.SETTLED:
        raise errors.cash_advance_already_settled_for_liquidation()

    # Owner-only: the actor's staff record must BE the advance's claimant.
    actor = await session.get(User, actor_user_id)
    if actor is None or actor.staff_id != advance.claimant_id:
        raise errors.not_advance_holder()

    existing = await liquidation_for_advance(session, cash_advance_id)
    if existing is not None:
        raise errors.liquidation_exists(
            claim_id=existing.id, ref_no=existing.ref_no
        )

    claim = await lifecycle.create_draft_claim(
        session,
        actor_user_id=actor_user_id,
        kind=st.LIQUIDATION_KIND,
        now=now,
    )
    # Prefill from the advance. `date_return` is deliberately copied rather than
    # left blank: it is the clock's origin, the traveller was already told the
    # deadline it produced, and a blank field they could retype differently
    # would silently describe a different trip than the one the advance funded.
    claim.dpo_no = advance.dpo_no
    claim.date_return = advance.date_return

    # Link BEFORE flushing anything else: link_claim mirrors deadline_date onto
    # the claim, which is what makes the seeded `deadline_check` and the
    # tracker's countdown ring live from the first read.
    #
    # The catch wraps `link_claim` rather than a trailing `flush()` because
    # link_claim is what WRITES `cash_advance_id` and flushes it — the 0020 belt
    # fires there, not later.
    try:
        await ca.link_claim(
            session, claim=claim, cash_advance=advance, actor_user_id=actor_user_id
        )
        # No-ops when the advance is already `liquidation_started` or `overdue` —
        # filing late does not un-late it, and the §89 slot stays held either way.
        await ca.mark_liquidation_started(
            session, cash_advance=advance, actor_user_id=actor_user_id
        )
        await session.flush()
    except IntegrityError as exc:
        # The 0020 belt caught a live liquidation the service check could not
        # see (a NULL-status row — see the docstring). Same named 409, minus the
        # claim id: this session is aborted and cannot query for the winner, and
        # naming the wrong claim would be worse than naming none.
        if "uq_reimb_claims_live_liquidation_per_advance" in str(exc.orig):
            raise errors.liquidation_exists(claim_id=None, ref_no=None) from exc
        raise
    return claim
