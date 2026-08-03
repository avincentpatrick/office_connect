"""The approver's decision endpoints — the module's ONE un-gated surface.

**The flag gates the module's surface; it never gates a decision on an instance
already in the chain.** ``require_feature`` is deliberately absent from this
router (api-standards §9, workflow-standards §9: ``execute_action`` never reads
the flag, so in-flight items always finish). Because FastAPI applies a router's
``dependencies`` to everything included beneath it, escaping the gate means a
SECOND top-level router — this one — mounted from ``main.py`` alongside the
gated one, not an ``include_router`` under it.

Everything else stays behind the 404 gate on purpose: reads and wizard writes
keep an OFF module indistinguishable from absent (fail-safe OFF), and
``/submit`` needs no exemption because ``start_instance`` already refuses new
instances flag-OFF. Its resubmit branch stays gated too — resubmit is
claimant-editing work, meaningless without the wizard behind it.

Route permission is the coarse ``reimb.claim.read``: the three gates carry
three different permissions (approve / review / fms_update), so no single route
dependency can express the real rule. The engine's ``resolve_authority`` is the
authorization of record and 403s ``workflow_not_authorized`` — the same
server-side-only doctrine ``can_read_claim`` follows.

One ``session.commit()`` per handler, response built before it (api-standards
§2, the wizard precedent).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.auth.dependencies import require_permission
from office_connect.core.auth.principal import Principal
from office_connect.core.db import get_session
from office_connect.modules.reimbursement.api.deps import claim_detail
from office_connect.modules.reimbursement.api.schemas import (
    ApproveIn,
    ClaimDetail,
    ReturnIn,
)
from office_connect.modules.reimbursement.services import lifecycle

router = APIRouter(prefix="/api/v1/reimbursement", tags=["reimbursement"])


@router.post("/claims/{claim_id}/approve", response_model=ClaimDetail)
async def approve_claim(
    claim_id: int,
    body: ApproveIn,
    principal: Principal = Depends(require_permission("reimb.claim.read")),
    session: AsyncSession = Depends(get_session),
):
    """Clear the current gate — the SAME action at every rung of the chain
    (``division_approval → admin_review → handed_to_fms → paid_closed``); only
    the button's label differs, and that is the FE's business. The engine
    decides whether this actor may act, whether the join is satisfied, and
    where the claim lands."""
    claim = await lifecycle.claim_action(
        session,
        claim_id=claim_id,
        action="approve",
        actor_user_id=principal.user_id,
        comment=body.comment,
        expected_version=body.expected_version,
    )
    detail = await claim_detail(session, claim, actor_user_id=principal.user_id)
    await session.commit()
    return detail


@router.post("/claims/{claim_id}/return", response_model=ClaimDetail)
async def return_claim(
    claim_id: int,
    body: ReturnIn,
    principal: Principal = Depends(require_permission("reimb.claim.read")),
    session: AsyncSession = Depends(get_session),
):
    """Bounce the claim back with structured reasons (spec §9.4). ``min_length``
    on the wire is only the first line — ``claim_action`` re-validates every id
    against the live taxonomy, because the service layer is what other callers
    (Celery, shell, future modules) go through."""
    claim = await lifecycle.claim_action(
        session,
        claim_id=claim_id,
        action="return",
        actor_user_id=principal.user_id,
        comment=body.comment,
        reason_ids=body.reason_ids,
        expected_version=body.expected_version,
    )
    detail = await claim_detail(session, claim, actor_user_id=principal.user_id)
    await session.commit()
    return detail
