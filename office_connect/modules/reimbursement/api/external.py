"""The FMS status relay — ``POST /claims/{id}/external-events``.

Spec §6.1 row 6's external leg: *With Budget → With Accounting → Payment
Processing (admin, **any order/skips allowed**)*. The Admin Officer phones FMS,
or FMS phones them, and this is where that conversation lands so the claimant
can see it on their tracker instead of asking.

**On the GATED router, deliberately.** api-standards §9a's un-gated exemption
exists so the feature flag can never refuse a decision on an instance already in
the chain — §9e's test is "would refusing it strand in-flight work?". A relay
strands nothing: the claim stays exactly where it was, and the update can be
recorded the moment the flag comes back on. Contrast ``/mark-paid``, which drives
a transition and therefore lives on the un-gated ``api/actions.py`` beside
``/settle``.

Coarse ``reimb.claim.read`` at the route with the exact rule in the handler
(api-standards §9): spec §3.2 gives "Set external FMS statuses" to the Admin
Officer and the System Admin, and ``reimb.claim.fms_update`` is the grant that
says so. The traveller whose claim it is gets a 403 here — reading their own
claim and speaking for FMS about it are different things.

One ``session.commit()`` per handler, response built before it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.auth.dependencies import require_permission
from office_connect.core.auth.principal import Principal
from office_connect.core.db import get_session
from office_connect.modules.reimbursement.api.deps import (
    can_read_claim,
    claim_detail,
    external_event_out,
    get_claim,
    has_scoped_grant,
)
from office_connect.modules.reimbursement.api.schemas import (
    ClaimDetail,
    ExternalEventIn,
    ExternalEventOut,
)
from office_connect.modules.reimbursement.services import errors, external

router = APIRouter()

#: Spec §3.2, as the grant data spells it.
_RELAY_PERMS = ("reimb.claim.fms_update",)


@router.post("/claims/{claim_id}/external-events", response_model=ClaimDetail)
async def record_external_event(
    claim_id: int,
    body: ExternalEventIn,
    principal: Principal = Depends(require_permission("reimb.claim.read")),
    session: AsyncSession = Depends(get_session),
):
    """Relay one FMS update. Appends; moves nothing.

    Returns the whole ``ClaimDetail`` rather than the created event, following
    every other write on this module's surface: the relay changes what the claim
    rail says, what the action set offers and what the tracker shows, and a
    client that had to refetch to learn that would render a moment of
    disagreement between the two.

    Refusal order matters. A caller who may not read the claim at all gets the
    404-shaped ``claim_not_found`` from ``get_claim``/``can_read_claim``, which is
    the module's standing no-existence-oracle rule; a caller who may READ it but
    may not speak for FMS gets the honest 403 that names whose job it is. The
    difference is safe because the second caller already knows the claim exists.
    """
    claim = await get_claim(session, claim_id)
    if not await can_read_claim(
        session, actor_user_id=principal.user_id, claim=claim
    ):
        raise errors.not_claim_owner()
    if not await has_scoped_grant(
        session,
        actor_user_id=principal.user_id,
        claim=claim,
        permissions=_RELAY_PERMS,
    ):
        raise errors.external_update_not_permitted()

    await external.record_external_event(
        session,
        claim_id=claim.id,
        status=body.status,
        actor_user_id=principal.user_id,
        noted_by=body.noted_by,
        note=body.note,
        event_date=body.event_date,
    )
    detail = await claim_detail(session, claim, actor_user_id=principal.user_id)
    await session.commit()
    return detail


@router.get(
    "/claims/{claim_id}/external-events", response_model=list[ExternalEventOut]
)
async def list_external_events(
    claim_id: int,
    principal: Principal = Depends(require_permission("reimb.claim.read")),
    session: AsyncSession = Depends(get_session),
):
    """The FMS journey on its own, oldest first.

    The tracker already merges these into its chronology, so this exists for the
    reader who wants the external leg by itself — "what has FMS actually told us
    about this packet" — without the bureau's own eight transitions in between.
    Claim-level read scoping, like every other read: the claimant sees their own.
    """
    claim = await get_claim(session, claim_id)
    if not await can_read_claim(
        session, actor_user_id=principal.user_id, claim=claim
    ):
        raise errors.not_claim_owner()
    events = await external.claim_events(session, claim.id)
    return [external_event_out(event) for event in events]
