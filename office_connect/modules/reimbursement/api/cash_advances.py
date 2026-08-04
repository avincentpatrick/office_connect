"""Cash-advance endpoints — the record COA's 30-day clock runs on (R-6-clock).

On the GATED router: an advance is new work, and flag-OFF the whole module is
indistinguishable from absent (api-standards §9). This is deliberately unlike
``api/actions.py``, whose exemption exists only so the flag can never refuse a
decision on an instance already in the chain (§9a) — recording an advance
starts a clock, it does not finish one.

Authorization follows §9's coarse-at-route / exact-in-service split:

- **Writes** gate on ``reimb.cash_advance.manage`` at the route, then check that
  the grant actually covers *this claimant's* org unit. Recording an advance is
  Accounting's act (R-6-clock kickoff decision) — ``dv_no``/``dv_date`` are data
  only Accounting holds, and the PD 1445 §89 one-at-a-time hard-block is only
  worth having if the record it guards is authoritative.
- **Reads** gate coarsely on ``reimb.claim.read`` and then apply the real rule in
  ``can_read_cash_advance``. The ``staff`` role's read grant is GLOBAL (spec
  §3.2), so route-level permission alone would publish every colleague's DV
  numbers and peso amounts to the whole bureau.

Transaction discipline is the house rule: services flush, each handler owns
exactly one ``commit()``, and the response is built BEFORE the commit so
post-commit attribute expiry cannot bite.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.auth.dependencies import require_permission
from office_connect.core.auth.principal import Principal
from office_connect.core.db import get_session
from office_connect.core.models import User
from office_connect.core.time import to_manila, utc_now
from office_connect.modules.reimbursement.api.deps import (
    can_manage_cash_advances,
    can_read_cash_advance,
    cash_advance_out,
    claim_detail,
)
from office_connect.modules.reimbursement.api.schemas import (
    CashAdvanceIn,
    CashAdvanceListOut,
    CashAdvanceOut,
    CashAdvancePatch,
    ClaimDetail,
)
from office_connect.modules.reimbursement.services import cash_advance as ca
from office_connect.modules.reimbursement.services import errors
from office_connect.modules.reimbursement.services import liquidation

router = APIRouter()


@router.post("/cash-advances", response_model=CashAdvanceOut, status_code=201)
async def create_cash_advance(
    body: CashAdvanceIn,
    principal: Principal = Depends(
        require_permission("reimb.cash_advance.manage")
    ),
    session: AsyncSession = Depends(get_session),
):
    """Record an advance and pin its liquidation deadline.

    A claimant who already holds an unliquidated advance yields a 409 naming the
    blocking DV and its deadline — PD 1445 §89 enforced as a DB index, surfaced
    as a sentence (§9.1 principle 4: never block without a path).
    """
    if not await can_manage_cash_advances(
        session, actor_user_id=principal.user_id, claimant_id=body.claimant_id
    ):
        raise errors.not_claim_owner()

    now = utc_now()
    advance = await ca.create_cash_advance(
        session,
        claimant_id=body.claimant_id,
        amount=body.amount,
        actor_user_id=principal.user_id,
        dv_no=body.dv_no,
        dv_date=body.dv_date,
        dpo_no=body.dpo_no,
        date_return=body.date_return,
        now=now,
    )
    today = to_manila(now).date()
    out = await cash_advance_out(
        session,
        advance,
        today=today,
        overdue_note=await ca.overdue_note(session, today=today),
    )
    await session.commit()
    return out


@router.post(
    "/cash-advances/{cash_advance_id}/liquidate",
    response_model=ClaimDetail,
    status_code=201,
)
async def liquidate_cash_advance(
    cash_advance_id: int,
    principal: Principal = Depends(require_permission("reimb.claim.create")),
    session: AsyncSession = Depends(get_session),
):
    """Open a draft liquidation against this advance — spec §9.3 step 1's
    *"Liquidate that instead?"*, offered where the advance actually lives.

    Gates on ``reimb.claim.create``, not ``cash_advance.manage``: this creates a
    CLAIM, and it is the traveller's to create. The route permission is the
    coarse half; the exact rule — the actor's staff record must BE the advance's
    claimant — lives in the service, because filing the liquidation IS
    certification A and A certifies about the claimant (api-standards §9's
    coarse-at-route / exact-in-service split).

    Returns the full ``ClaimDetail``, so the client navigates straight into the
    wizard on the same response that created the draft.
    """
    now = utc_now()
    claim = await liquidation.start_liquidation(
        session,
        cash_advance_id=cash_advance_id,
        actor_user_id=principal.user_id,
        now=now,
    )
    # Built BEFORE the commit — post-commit attribute expiry would re-query
    # every relationship this mapper touches (the house rule, §"Transaction
    # discipline" in this module's docstring).
    out = await claim_detail(session, claim, actor_user_id=principal.user_id)
    await session.commit()
    return out


@router.get("/cash-advances", response_model=CashAdvanceListOut)
async def list_cash_advances(
    claimant_id: int | None = Query(default=None),
    principal: Principal = Depends(require_permission("reimb.claim.read")),
    session: AsyncSession = Depends(get_session),
):
    """Advances the caller may see.

    With no ``claimant_id`` this answers "mine" — resolved from the caller's own
    staff link, never from a client-supplied id. An explicit ``claimant_id`` is
    authorized per row, so the endpoint can serve both the traveller's My-Work
    card and Accounting's queue without a second route or a mode flag.
    """
    actor = await session.get(User, principal.user_id)
    target = claimant_id if claimant_id is not None else (actor.staff_id if actor else None)
    if target is None:
        # A login with no staff record has no advances by construction — an
        # empty list, not a 4xx: nothing is wrong, there is simply nothing.
        return CashAdvanceListOut(items=[])
    if not await can_read_cash_advance(
        session, actor_user_id=principal.user_id, claimant_id=target
    ):
        raise errors.not_claim_owner()

    today = to_manila(utc_now()).date()
    note = await ca.overdue_note(session, today=today)
    rows = await ca.list_cash_advances(session, claimant_id=target)
    return CashAdvanceListOut(
        items=[
            await cash_advance_out(session, row, today=today, overdue_note=note)
            for row in rows
        ]
    )


@router.get("/cash-advances/{cash_advance_id}", response_model=CashAdvanceOut)
async def read_cash_advance(
    cash_advance_id: int,
    principal: Principal = Depends(require_permission("reimb.claim.read")),
    session: AsyncSession = Depends(get_session),
):
    advance = await ca.get_cash_advance(session, cash_advance_id)
    if not await can_read_cash_advance(
        session, actor_user_id=principal.user_id, claimant_id=advance.claimant_id
    ):
        # The same slug the write paths use — a refused reader learns nothing
        # about whether the row exists.
        raise errors.not_claim_owner()
    today = to_manila(utc_now()).date()
    return await cash_advance_out(
        session,
        advance,
        today=today,
        overdue_note=await ca.overdue_note(session, today=today),
    )


@router.patch("/cash-advances/{cash_advance_id}", response_model=CashAdvanceOut)
async def update_cash_advance(
    cash_advance_id: int,
    body: CashAdvancePatch,
    principal: Principal = Depends(
        require_permission("reimb.cash_advance.manage")
    ),
    session: AsyncSession = Depends(get_session),
):
    """Correct a recorded advance. Moving ``date_return`` re-pins the deadline
    and re-mirrors it onto every linked claim; nothing else disturbs the clock."""
    advance = await ca.get_cash_advance(session, cash_advance_id)
    if not await can_manage_cash_advances(
        session, actor_user_id=principal.user_id, claimant_id=advance.claimant_id
    ):
        raise errors.not_claim_owner()

    now = utc_now()
    before = advance.deadline_date
    advance = await ca.update_cash_advance(
        session,
        cash_advance_id=cash_advance_id,
        actor_user_id=principal.user_id,
        fields=body.model_dump(exclude_unset=True),
        now=now,
    )
    # Fan-out lives here, not in the service, so the single-table writer stays
    # single-table and the mirror update is visible at its call site.
    if advance.deadline_date != before:
        await ca.remirror_deadline(session, cash_advance=advance)

    today = to_manila(now).date()
    out = await cash_advance_out(
        session,
        advance,
        today=today,
        overdue_note=await ca.overdue_note(session, today=today),
    )
    await session.commit()
    return out
