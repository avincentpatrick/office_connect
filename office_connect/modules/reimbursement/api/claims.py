"""The claim wizard endpoints — the module's draft CRUD + compute + submit.

Transaction discipline: every service flushes and never commits; each handler
here owns exactly ONE ``session.commit()`` (api-standards §2, the directory
precedent). The ``ClaimDetail`` response is built BEFORE the commit so
post-commit attribute expiry can't bite. Status/holder/ref writes stay inside
``services/lifecycle.py`` (workflow-standards §1); business-field writes stay
inside ``services/drafts.py`` — this layer only composes them.
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
    get_claim,
)
from office_connect.modules.reimbursement.api.schemas import (
    CancelIn,
    ClaimDetail,
    ClaimDraftIn,
    ClaimPatch,
    LegsReplaceIn,
)
from office_connect.modules.reimbursement.services import drafts, lifecycle
from office_connect.modules.reimbursement.services import errors
from office_connect.modules.reimbursement.services import status as st

router = APIRouter()


@router.post("/claims", response_model=ClaimDetail, status_code=201)
async def create_claim(
    body: ClaimDraftIn,
    principal: Principal = Depends(require_permission("reimb.claim.create")),
    session: AsyncSession = Depends(get_session),
):
    """Create a draft for the caller's own staff record (directory prefill is
    server-side: claimant identity + ``is_jo_cos`` derive from the directory,
    WCAG 2.2 §3.3.7). Draft birth + optional prefill land in ONE transaction —
    a prefill validation failure rolls the draft row back too (no orphan)."""
    claim = await lifecycle.create_draft_claim(
        session, actor_user_id=principal.user_id
    )
    changes = body.model_dump(exclude_unset=True)
    if changes:
        claim = await drafts.update_draft_fields(
            session,
            claim_id=claim.id,
            actor_user_id=principal.user_id,
            changes=changes,
        )
    detail = await claim_detail(session, claim)
    await session.commit()
    return detail


@router.get("/claims/{claim_id}", response_model=ClaimDetail)
async def read_claim(
    claim_id: int,
    principal: Principal = Depends(require_permission("reimb.claim.read")),
    session: AsyncSession = Depends(get_session),
):
    claim = await get_claim(session, claim_id)
    if not await can_read_claim(
        session, actor_user_id=principal.user_id, claim=claim
    ):
        # Same slug as the write paths — no owner-vs-scope information leak.
        raise errors.not_claim_owner()
    return await claim_detail(session, claim)


@router.patch("/claims/{claim_id}", response_model=ClaimDetail)
async def update_claim(
    claim_id: int,
    body: ClaimPatch,
    principal: Principal = Depends(require_permission("reimb.claim.create")),
    session: AsyncSession = Depends(get_session),
):
    claim = await drafts.update_draft_fields(
        session,
        claim_id=claim_id,
        actor_user_id=principal.user_id,
        changes=body.model_dump(exclude_unset=True),
    )
    detail = await claim_detail(session, claim)
    await session.commit()
    return detail


@router.put("/claims/{claim_id}/legs", response_model=ClaimDetail)
async def replace_legs(
    claim_id: int,
    body: LegsReplaceIn,
    principal: Principal = Depends(require_permission("reimb.claim.create")),
    session: AsyncSession = Depends(get_session),
):
    claim = await drafts.replace_legs(
        session,
        claim_id=claim_id,
        actor_user_id=principal.user_id,
        legs=[leg.model_dump() for leg in body.legs],
    )
    detail = await claim_detail(session, claim)
    await session.commit()
    return detail


@router.post("/claims/{claim_id}/compute", response_model=ClaimDetail)
async def compute_claim(
    claim_id: int,
    principal: Principal = Depends(require_permission("reimb.claim.create")),
    session: AsyncSession = Depends(get_session),
):
    """The money step's refresh: recompute server-side and RETURN the totals —
    the client never does money math (empty request body by design;
    ``other_total`` is a claim field edited via PATCH)."""
    claim = await drafts.recompute_totals(
        session, claim_id=claim_id, actor_user_id=principal.user_id
    )
    detail = await claim_detail(session, claim)
    await session.commit()
    return detail


@router.post("/claims/{claim_id}/submit", response_model=ClaimDetail)
async def submit_claim(
    claim_id: int,
    principal: Principal = Depends(require_permission("reimb.claim.submit")),
    session: AsyncSession = Depends(get_session),
):
    """Send the packet forward. A ``returned`` claim resubmits (same button on
    the FE — fix-and-resubmit re-enters the chain at step 1 with a fresh
    revision); anything else is the first submit via the atomic
    ``lifecycle.submit_claim`` (do NOT reimplement). The pre-lock status read
    only picks the path — both services re-check under the row lock."""
    claim = await get_claim(session, claim_id)
    if (claim.status or st.DRAFT) == st.RETURNED:
        claim = await lifecycle.claim_action(
            session,
            claim_id=claim_id,
            action="resubmit",
            actor_user_id=principal.user_id,
        )
    else:
        claim = await lifecycle.submit_claim(
            session, claim_id=claim_id, actor_user_id=principal.user_id
        )
    detail = await claim_detail(session, claim)
    await session.commit()
    return detail


@router.post("/claims/{claim_id}/cancel", response_model=ClaimDetail)
async def cancel_claim(
    claim_id: int,
    body: CancelIn,
    principal: Principal = Depends(require_permission("reimb.claim.create")),
    session: AsyncSession = Depends(get_session),
):
    """Cancel a never-submitted draft (owner-only, reason mandatory — spec
    §6.1 row 9). Post-submit cancellation goes through the workflow's own
    returned→cancelled transition in a later increment."""
    claim = await lifecycle.cancel_draft_claim(
        session,
        claim_id=claim_id,
        actor_user_id=principal.user_id,
        comment=body.comment,
    )
    detail = await claim_detail(session, claim)
    await session.commit()
    return detail
