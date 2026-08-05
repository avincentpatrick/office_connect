"""The oversight queue — ``GET /claims``, the module's first LIST endpoint.

Spec §7 rule 5: *"Stalls are visible, not silent … The Admin Officer's queue
includes an 'External > 10 working days' filter for FMS follow-ups."* This is
that queue, and it exists because of a hole R-4-app left open by construction: a
claim at ``handed_to_fms`` has ``holder_kind='external_fms'`` and
``holder_id=NULL``, so ``/my-work``'s holder-keyed lists show it to **nobody**.
The Admin Officer who handed the packet to FMS had, until now, no surface that
ever showed it again.

Why this route is not just "My Work with filters": My Work is *self-keyed*
(holder = me, or claimant = me), so it needs no scope check at all — nothing
another user owns can appear. This one is keyed on somebody ELSE's claims, which
makes it the first endpoint where org scope is load-bearing rather than
incidental. See ``services/queue.py`` for why that scope is NOT
``reimb.claim.read``.

Gated router, deliberately: api-standards §9a's un-gated exemption exists so the
feature flag can never refuse a decision on an instance already in the chain.
Refusing a *read* strands nothing, so §9e's test says this stays behind the flag
like the rest of the module's surface.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.auth.dependencies import require_permission
from office_connect.core.auth.principal import Principal
from office_connect.core.db import get_session
from office_connect.core.time import utc_now
from office_connect.modules.reimbursement.api.deps import (
    claimant_names,
    holder_names,
    work_item,
)
from office_connect.modules.reimbursement.api.schemas import (
    ClaimQueueOut,
    QueueItemOut,
)
from office_connect.modules.reimbursement.models import ReimbClaim
from office_connect.modules.reimbursement.services import (
    actions,
    errors,
    external,
    queue,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/claims", response_model=ClaimQueueOut)
async def list_claims(
    kind: str | None = Query(default=None),
    status: str | None = Query(default=None),
    claimant_id: int | None = Query(default=None),
    external_over: bool = Query(
        default=False,
        description="Only claims with FMS longer than the follow-up threshold.",
    ),
    limit: int = Query(default=queue.DEFAULT_LIMIT),
    offset: int = Query(default=0),
    principal: Principal = Depends(require_permission("reimb.claim.read")),
    session: AsyncSession = Depends(get_session),
):
    """Live, submitted claims this actor oversees.

    Coarse ``reimb.claim.read`` at the route like every sibling, with the real
    rule in the service — except that here "the real rule" is a whole different
    permission set, not a narrowing of the route's. That is deliberate and is
    the point of ``queue.OVERSIGHT_PERMS``: the route gate proves the caller is
    inside the module at all, and ``oversight_scope`` decides whether they are
    an overseer of anyone.

    ``external_over`` is the spec §7 rule 5 filter. It is applied in Python
    rather than SQL because the count is in Manila WORKING days against the
    holiday calendar — expressible in SQL only by reimplementing
    ``core/workdays`` in Postgres, which is exactly the duplication rule 10
    forbids. The page is capped, the holiday window is loaded once, and the
    filter narrows a set the scope clause has already bounded.
    """
    now = utc_now()
    is_global, unit_ids = await queue.oversight_scope(
        session, principal.user_id, now=now
    )
    if not is_global and not unit_ids:
        raise errors.queue_not_permitted()

    threshold = await queue.followup_threshold(session)
    stmt = queue.base_query(
        is_global=is_global,
        unit_ids=unit_ids,
        kind=kind,
        statuses=(status,) if status else None,
        claimant_id=claimant_id,
    )

    if external_over:
        # The filter decides membership, so it must run before the page is cut:
        # paginating first would drop stalled claims off page 2 and report a
        # total that answers a question nobody asked.
        #
        # The scan is capped, and the cap is safe because of the ORDER: longest-
        # waiting first means every claim over the threshold sorts ahead of
        # every claim under it, so truncation can only ever drop rows that were
        # going to be filtered out anyway. It bites only if more than
        # EXTERNAL_SCAN_CAP claims are simultaneously stalled with FMS — at
        # which point the count is the story, not the list — and it says so out
        # loud rather than quietly showing a short queue.
        rows = list(
            (
                await session.execute(
                    stmt.where(ReimbClaim.holder_kind == "external_fms")
                    .order_by(ReimbClaim.holder_since.asc().nulls_last())
                    .limit(queue.EXTERNAL_SCAN_CAP)
                )
            )
            .scalars()
            .all()
        )
        if len(rows) == queue.EXTERNAL_SCAN_CAP:
            logger.warning(
                "reimb.queue.external_scan_capped cap=%s actor=%s — the FMS "
                "follow-up list may be incomplete.",
                queue.EXTERNAL_SCAN_CAP,
                principal.user_id,
            )
        fms_days = await queue.days_with_fms(session, rows, now=now)
        matched = [c for c in rows if fms_days.get(c.id, 0) > threshold]
        total = len(matched)
        page = matched[max(offset, 0) : max(offset, 0) + min(limit, queue.MAX_LIMIT)]
    else:
        total = (
            await session.execute(
                select(func.count()).select_from(stmt.subquery())
            )
        ).scalar_one()
        page = list(
            (
                await session.execute(
                    stmt.order_by(
                        ReimbClaim.holder_since.asc().nulls_last(),
                        ReimbClaim.id.asc(),
                    )
                    .limit(min(limit, queue.MAX_LIMIT))
                    .offset(max(offset, 0))
                )
            )
            .scalars()
            .all()
        )
        fms_days = await queue.days_with_fms(session, page, now=now)

    holders = await holder_names(session, page)
    claimants = await claimant_names(session, page)
    # One DISTINCT ON for the whole page (R-7-events). "12 working days with FMS"
    # and "…and the last we heard it was With Accounting" are different facts,
    # and the second is what decides whether the follow-up call is worth making.
    fms_latest = await external.latest_events(session, [c.id for c in page])
    due = await actions.active_step_due_dates(
        session,
        [c.workflow_instance_id for c in page if c.workflow_instance_id is not None],
    )

    def _holder_display(claim: ReimbClaim) -> str | None:
        if claim.holder_kind == "external_fms":
            return "FMS"
        if claim.holder_kind == "user" and claim.holder_id is not None:
            if claim.holder_id == principal.user_id:
                return "You"
            return holders.get(claim.holder_id)
        return None

    items: list[QueueItemOut] = []
    for claim in page:
        base = work_item(
            claim,
            holder_display=_holder_display(claim),
            now=now,
            sla_due_at=(
                due.get(claim.workflow_instance_id)
                if claim.workflow_instance_id is not None
                else None
            ),
        )
        days = fms_days.get(claim.id)
        latest = fms_latest.get(claim.id)
        items.append(
            QueueItemOut(
                **base.model_dump(),
                claimant_display=claimants.get(claim.claimant_id),
                days_with_fms=days,
                external_followup=days is not None and days > threshold,
                external_status_label=(
                    external.label(latest.status) if latest is not None else None
                ),
            )
        )

    # Spec §7 rule 5: "anything Overdue sorts to top". The SQL already ordered
    # longest-waiting-first; this lifts the two urgency classes above it without
    # disturbing that order within each class (Python sort is stable).
    items.sort(
        key=lambda i: (
            not i.external_followup and i.sla_state != actions.OVERDUE,
        )
    )

    return ClaimQueueOut(
        items=items, total=total, followup_working_days=threshold
    )
