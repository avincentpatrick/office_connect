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
from office_connect.modules.reimbursement.api.deps import (
    can_manage_cash_advances,
    claim_detail,
    get_claim,
    has_scoped_grant,
)
from office_connect.modules.reimbursement.api.schemas import (
    ApproveIn,
    ClaimDetail,
    MarkPaidIn,
    ReturnIn,
    SettleIn,
)
from office_connect.modules.reimbursement.services import (
    errors,
    external,
    lifecycle,
    settlement,
)

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


@router.post("/claims/{claim_id}/mark-paid", response_model=ClaimDetail)
async def mark_claim_paid(
    claim_id: int,
    body: MarkPaidIn,
    principal: Principal = Depends(require_permission("reimb.claim.read")),
    session: AsyncSession = Depends(get_session),
):
    """Close a reimbursement, recording what FMS paid (spec §6.1 row 8).

    **On this router, not the gated one** — the ``/settle`` argument, one chain
    over. Marking paid is a decision on an instance already in the chain, the
    exact case the flag must never gate; behind ``require_feature`` a flag-OFF
    would 404 this route and strand every claim at ``handed_to_fms`` with FMS
    having already paid it and no way to say so.

    Coarse ``reimb.claim.read`` at the route like its siblings, with the real
    rule below: spec §3.2 gives "Record settlement (refund OR / payout)" to the
    Admin Officer and the System Admin, and ``reimb.claim.fms_update`` is the
    grant the FMS leg is authorized on throughout — the same permission the
    ``handed_to_fms`` gate itself requires, so this check and the engine's
    ``resolve_authority`` agree by construction rather than by coincidence.
    """
    claim = await get_claim(session, claim_id)
    if not await has_scoped_grant(
        session,
        actor_user_id=principal.user_id,
        claim=claim,
        permissions=("reimb.claim.fms_update",),
    ):
        raise errors.external_update_not_permitted()
    paid = await external.record_payout(
        session,
        claim_id=claim_id,
        actor_user_id=principal.user_id,
        payout_ref=body.payout_ref,
        paid_on=body.paid_on,
        comment=body.comment,
        expected_version=body.expected_version,
    )
    detail = await claim_detail(session, paid, actor_user_id=principal.user_id)
    await session.commit()
    return detail


@router.post("/claims/{claim_id}/settle", response_model=ClaimDetail)
async def settle_claim(
    claim_id: int,
    body: SettleIn,
    principal: Principal = Depends(require_permission("reimb.claim.read")),
    session: AsyncSession = Depends(get_session),
):
    """Close a liquidation, recording how its money came out (spec §6.2).

    **On this router, not the gated one.** Settlement is a decision on an
    instance already in the chain — the exact case the flag must never gate.
    Behind ``require_feature`` a flag-OFF would 404 this route and strand every
    liquidation at ``handed_to_fms``, each one still holding its claimant's PD
    1445 §89 slot with no way to release it.

    Coarse ``reimb.claim.read`` at the route like its siblings, with the real
    rule below: spec §3.2 gives "Record settlement (refund OR / payout)" to the
    Admin Officer and the System Admin, and ``can_manage_cash_advances`` is the
    same org-scoped check the cash-advance writes use. The engine's
    ``resolve_authority`` then remains the authorization of record for the
    transition this drives — two gates, and both must pass.
    """
    claim = await get_claim(session, claim_id)
    if not await can_manage_cash_advances(
        session, actor_user_id=principal.user_id, claimant_id=claim.claimant_id
    ):
        raise errors.not_claim_owner()
    settled = await settlement.record_settlement(
        session,
        claim_id=claim_id,
        actor_user_id=principal.user_id,
        or_no=body.or_no,
        or_date=body.or_date,
        refund_amount=body.refund_amount,
        comment=body.comment,
        expected_version=body.expected_version,
    )
    detail = await claim_detail(session, settled, actor_user_id=principal.user_id)
    await session.commit()
    return detail
