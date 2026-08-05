"""Insights — the comment-learning loop's HTTP surface (spec §11, R-8).

Three routes: read the ranking, promote a reason, demote it.

**Why ``/insights`` and not ``/claims/insights``.** api-standards §9g: the
literal segment would sit under ``claims.router``'s ``GET /claims/{claim_id}``,
which is included first and matches on registration order — the request would be
read as a claim whose id is ``"insights"`` and 422 on validation. A view over a
set gets its own segment, which is order-independent by construction and also
honest: this is not a claim.

**The read rule is the board's, unchanged.** api-standards §9f — a list may not
borrow a row's read rule, and an aggregate is a list with the rows taken away.
The route gate stays the coarse ``reimb.claim.read`` (globally granted to every
traveller, so it proves only that the caller is inside the module at all); the
real rule is ``queue.oversight_scope``, and the aggregate spans exactly the
claims the actor could already open one at a time. That is api-standards §9h's
whole content: **the scope IS the privacy boundary.**

**The write rule is narrower than the read rule**, which no surface in this
module has needed before. Reading the ranking makes you an overseer of somebody;
promoting changes what every claimant in the agency sees. So the button is gated
on an agency-wide ``reimb.claim.review`` grant and ``can_promote`` rides the
envelope, because the R-4-screens doctrine is that the UI is never offered a
button certain to be refused.

Gated router, like the queue and the board: §9a's un-gated exemption exists so
the feature flag can never refuse a decision on an instance already in the
chain. Refusing a read, or an edit to a config catalog, strands nothing.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.auth.dependencies import require_permission
from office_connect.core.auth.principal import Principal
from office_connect.core.db import get_session
from office_connect.core.time import utc_now
from office_connect.modules.reimbursement.api.schemas import (
    ReasonRankOut,
    ReturnInsightsOut,
)
from office_connect.modules.reimbursement.services import errors, insights, queue

router = APIRouter()


def _rank_out(item: insights.ReasonRank) -> ReasonRankOut:
    return ReasonRankOut(
        reason_id=item.reason_id,
        code=item.code,
        label=item.label,
        category=item.category,
        count=item.count,
        prior_count=item.prior_count,
        trend=item.trend,
        promoted=item.promoted,
        promotable=item.is_active,
    )


@router.get("/insights/return-reasons", response_model=ReturnInsightsOut)
async def return_insights(
    principal: Principal = Depends(require_permission("reimb.claim.read")),
    session: AsyncSession = Depends(get_session),
):
    """Spec §11: return reasons ranked by 90-day count, with trend.

    The module's first surface whose whole purpose is aggregating other people's
    work, so the refusal matters as much as the answer. An actor who oversees
    nobody is refused — not handed ``200 []``, which would assert "nothing comes
    back for any reason", a claim about the world that is false. The refusal
    names what they CAN see (their own returns, with reasons, on each claim's
    tracker), per spec §9.1 principle 4.
    """
    now = utc_now()
    is_global, unit_ids = await queue.oversight_scope(
        session, principal.user_id, now=now
    )
    if not is_global and not unit_ids:
        raise errors.insights_not_permitted()

    data = await insights.ranked_reasons(
        session, is_global=is_global, unit_ids=unit_ids, now=now
    )
    return ReturnInsightsOut(
        window_days=data.window_days,
        period_start=data.period_start,
        total_returns=data.total_returns,
        can_promote=await insights.may_promote(session, principal.user_id, now=now),
        items=[_rank_out(item) for item in data.items],
    )


async def _promote(
    session: AsyncSession, *, principal: Principal, reason_id: int, promoted: bool
) -> ReturnInsightsOut:
    """The shared body of promote/demote — authorize, write, answer with the
    whole surface refreshed.

    Returning the full ranking rather than the one row it changed follows the
    same rule as every mutation in this module (delta row 59): one response
    carries the record AND the state the screen must now show, so there is no
    window in which the button and the list disagree.
    """
    now = utc_now()
    if not await insights.may_promote(session, principal.user_id, now=now):
        raise errors.promotion_not_permitted()

    await insights.set_promoted(
        session,
        reason_id=reason_id,
        promoted=promoted,
        actor_user_id=principal.user_id,
    )
    # Scope is resolved AFTER the write and from the same actor: a promoter is
    # by definition global, but reading their scope here rather than assuming it
    # keeps the two rules independent, so narrowing one later cannot silently
    # widen the other.
    is_global, unit_ids = await queue.oversight_scope(
        session, principal.user_id, now=now
    )
    data = await insights.ranked_reasons(
        session, is_global=is_global, unit_ids=unit_ids, now=now
    )
    await session.commit()
    return ReturnInsightsOut(
        window_days=data.window_days,
        period_start=data.period_start,
        total_returns=data.total_returns,
        can_promote=True,
        items=[_rank_out(item) for item in data.items],
    )


@router.post(
    "/insights/return-reasons/{reason_id}/promote",
    response_model=ReturnInsightsOut,
)
async def promote_reason(
    reason_id: int,
    principal: Principal = Depends(require_permission("reimb.claim.review")),
    session: AsyncSession = Depends(get_session),
):
    """Spec §11's "promote to pre-check" — one click, no deploy.

    All this writes is ``reimb_return_reason_catalogs.promoted_check``. The
    wizard reads that flag through ``GET /return-reasons`` and renders an
    advisory at step 5, so the whole path from this POST to a claimant seeing
    the warning is a DATA change (rule 10 + spec §14's R-8 sentence).

    **The warning is advisory and can never gate.** R-3's hard gate is about
    MISSING DOCUMENTS; conflating "often returned" with "incomplete" would let a
    statistic refuse a legitimate claim. Nothing this endpoint writes is read by
    ``checklist.assert_packet_complete``, and that separation is the guarantee —
    not a promise in the copy.
    """
    return await _promote(
        session, principal=principal, reason_id=reason_id, promoted=True
    )


@router.post(
    "/insights/return-reasons/{reason_id}/demote",
    response_model=ReturnInsightsOut,
)
async def demote_reason(
    reason_id: int,
    principal: Principal = Depends(require_permission("reimb.claim.review")),
    session: AsyncSession = Depends(get_session),
):
    """Switch a promoted warning back off.

    A first-class verb, not an afterthought: a promotion that could not be
    undone would make every promotion a decision nobody wants to be the first to
    make. It is also the only way to retire a warning whose reason has since
    been deactivated, which is why ``set_promoted`` gates the active check on
    the promote direction alone.
    """
    return await _promote(
        session, principal=principal, reason_id=reason_id, promoted=False
    )
