"""The oversight surfaces — ``GET /claims`` (the queue) and ``GET /board``.

Two lenses on one set of rows, sharing one scope rule and one row mapper.
``GET /claims`` was the module's first LIST endpoint (R-7-queue); ``GET /board``
is spec §9.6's pipeline board (R-7-board), which is the same list with counts
and peso totals over it.

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
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.auth.dependencies import require_permission
from office_connect.core.auth.principal import Principal
from office_connect.core.db import get_session
from office_connect.core.money import money_str
from office_connect.core.time import utc_now
from office_connect.modules.reimbursement.api.deps import (
    claimant_names,
    holder_names,
    work_item,
)
from office_connect.modules.reimbursement.api.schemas import (
    BoardColumnOut,
    ClaimBoardOut,
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
from office_connect.modules.reimbursement.services import status as st

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

    items = await _queue_rows(
        session, page, principal=principal, now=now, threshold=threshold,
        fms_days=fms_days,
    )
    return ClaimQueueOut(
        items=_urgency_first(items), total=total, followup_working_days=threshold
    )


async def _queue_rows(
    session: AsyncSession,
    claims: list[ReimbClaim],
    *,
    principal: Principal,
    now: datetime,
    threshold: int,
    fms_days: dict[int, int] | None = None,
) -> list[QueueItemOut]:
    """A set of claims as oversight rows, with every lookup batched ONCE.

    Extracted at R-7-board so the board is a third lens on the same row rather
    than a second copy of this block. Delta row 140's rule ("two mappers for one
    row shape is how two lists drift") applies to the batching too: three
    columns each doing their own holiday load, ``DISTINCT ON`` and due-date
    query would be nine round-trips for one screen, and the first one to be
    optimized would start answering a different question from the others.

    ``fms_days`` is passed in when the caller has already computed it for a
    different set (the queue's ``external_over`` branch filters on it before
    paging); otherwise it is loaded here, once, for everything given.
    """
    if not claims:
        return []
    if fms_days is None:
        fms_days = await queue.days_with_fms(session, claims, now=now)
    holders = await holder_names(session, claims)
    claimants = await claimant_names(session, claims)
    # One DISTINCT ON for the whole set (R-7-events). "12 working days with FMS"
    # and "…and the last we heard it was With Accounting" are different facts,
    # and the second is what decides whether the follow-up call is worth making.
    fms_latest = await external.latest_events(session, [c.id for c in claims])
    due = await actions.active_step_due_dates(
        session,
        [c.workflow_instance_id for c in claims if c.workflow_instance_id is not None],
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
    for claim in claims:
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
    return items


def _urgency_first(items: list[QueueItemOut]) -> list[QueueItemOut]:
    """Spec §7 rule 5 / §9.6: "anything Overdue sorts to top".

    The SQL already ordered the set; this lifts the two urgency classes above it
    without disturbing that order within each class (Python sort is stable), so
    a column stays longest-waiting-first underneath the claims that need
    chasing.
    """
    return sorted(
        items,
        key=lambda i: (not i.external_followup and i.sla_state != actions.OVERDUE,),
    )


@router.get("/board", response_model=ClaimBoardOut)
async def claim_board(
    principal: Principal = Depends(require_permission("reimb.claim.read")),
    session: AsyncSession = Depends(get_session),
):
    """The pipeline board — spec §9.6, the module's public face.

    Three columns of status GROUPS with a count and a peso total on each header.
    My Work answers "what is mine" and the queue answers "what is stuck"; this
    answers the question a bureau chief asks from across the room, which is
    **how much is where**.

    Same read rule as the queue, deliberately: api-standards §9f says a list may
    not borrow a row's read rule, and a board is a list with headers. Anyone who
    oversees nobody is refused with the queue's own sentence rather than a
    second one — and the refusal matters more here than there, because this is
    the first surface whose HEADLINE is aggregated peso data.

    **Why ``/board`` and not ``/claims/board``:** ``claims.router`` is included
    before this one and declares ``GET /claims/{claim_id}``, which FastAPI
    matches first — a literal segment under ``/claims/`` would be swallowed and
    422 on ``claim_id="board"``. Making it work would mean pinning router
    include order, which is not a contract anyone can see. A sibling segment is
    correct by construction (api-standards §9g).
    """
    now = utc_now()
    is_global, unit_ids = await queue.oversight_scope(
        session, principal.user_id, now=now
    )
    if not is_global and not unit_ids:
        raise errors.queue_not_permitted()

    threshold = await queue.followup_threshold(session)
    window = await queue.done_window_days(session)
    cutoff = queue.done_cutoff(now, window)

    totals, unmapped = await queue.column_totals(
        session, is_global=is_global, unit_ids=unit_ids, cutoff=cutoff
    )
    for status, count in unmapped.items():
        # Cannot happen while every state declares a column
        # (`status._assert_board_columns` refuses otherwise) — but a status code
        # left over from a retired definition version would land here, and the
        # failure mode is money missing from a total with nothing on screen to
        # say so. Spec §14 grades this surface on "board totals match DB".
        logger.warning(
            "reimb.board.unmapped_status status=%s count=%s actor=%s — these "
            "claims are in no column and are missing from the board totals.",
            status,
            count,
            principal.user_id,
        )

    cards: dict[str, list[ReimbClaim]] = {}
    for column, _label in st.BOARD_COLUMNS:
        cards[column] = list(
            (
                await session.execute(
                    queue.board_card_query(
                        is_global=is_global,
                        unit_ids=unit_ids,
                        column=column,
                        cutoff=cutoff,
                    )
                )
            )
            .scalars()
            .all()
        )

    # ONE pass over every card on the board — one holiday window, one DISTINCT
    # ON, one due-date query for all three columns rather than three of each.
    flat = [claim for column, _ in st.BOARD_COLUMNS for claim in cards[column]]
    rows = {
        row.id: row
        for row in await _queue_rows(
            session, flat, principal=principal, now=now, threshold=threshold
        )
    }

    def _column(column: str, label: str) -> BoardColumnOut:
        ordered = [rows[c.id] for c in cards[column] if c.id in rows]
        return BoardColumnOut(
            key=column,
            label=label,
            count=totals[column][0],
            total=money_str(totals[column][1]),
            # Done keeps the SQL's most-recently-finished order. The urgency
            # lift is for work that still needs chasing, and lifting a finished
            # claim over a more recently finished one would answer a question
            # nobody asked of a Done column.
            items=ordered if column == st.BOARD_DONE else _urgency_first(ordered),
        )

    return ClaimBoardOut(
        columns=[_column(column, label) for column, label in st.BOARD_COLUMNS],
        followup_working_days=threshold,
        card_limit=queue.BOARD_CARD_LIMIT,
        done_window_days=window,
    )
