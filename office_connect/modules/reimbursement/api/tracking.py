"""The claim tracker feed + the return dialog's taxonomy.

``GET /claims/{id}/timeline`` is the spec §9.2 claim-tracker source: every
transition from the append-only ``reimb_status_histories``, with the return
reasons attached to the rows a return produced (spec §12 — the claimant sees
the reasons verbatim, not a paraphrase).

Pairing note: history rows and ``reimb_return_events`` have no FK between them,
but they are written 1:1 in the same transaction by ``claim_action`` — and a
row landing in ``returned``/``fms_returned`` is *only* ever reachable by the
``return`` action (``resubmit`` leaves ``returned`` for ``division_approval``).
So the k-th return-status row is the k-th return event. The zip is defensive: a
count mismatch drops the reasons rather than attaching them to the wrong
return, because a misattributed reason is worse than a missing one.

``GET /return-reasons`` mirrors ``reference.py::list_regions`` — a bounded,
seeded lookup behind the module's read permission.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.auth.dependencies import require_permission
from office_connect.core.auth.principal import Principal
from office_connect.core.db import get_session
from office_connect.core.models import Staff, User
from office_connect.modules.reimbursement.api.deps import (
    can_read_claim,
    get_claim,
)
from office_connect.modules.reimbursement.api.schemas import (
    ReturnReasonOut,
    TimelineEventOut,
)
from office_connect.modules.reimbursement.models import (
    ReimbReturnEvent,
    ReimbReturnReasonCatalog,
    ReimbStatusHistory,
)
from office_connect.modules.reimbursement.services import errors
from office_connect.modules.reimbursement.services import status as st

router = APIRouter()

# The statuses only a `return` action can produce (module workflow v1).
_RETURN_STATUSES = (st.RETURNED, st.FMS_RETURNED)


def _reason_out(row: ReimbReturnReasonCatalog) -> ReturnReasonOut:
    return ReturnReasonOut(
        id=row.id, code=row.code, label=row.label, category=row.category
    )


async def _actor_names(
    session: AsyncSession, user_ids: set[int]
) -> dict[int, str]:
    """One batched user→display-name lookup. ``include_deleted`` so a claim's
    history keeps rendering after the actor is offboarded."""
    if not user_ids:
        return {}
    rows = (
        await session.execute(
            select(User.id, User.email, Staff.full_name)
            .join(Staff, Staff.id == User.staff_id, isouter=True)
            .where(User.id.in_(user_ids))
            .execution_options(include_deleted=True)
        )
    ).all()
    return {uid: (full_name or email) for uid, email, full_name in rows}


@router.get("/claims/{claim_id}/timeline", response_model=list[TimelineEventOut])
async def claim_timeline(
    claim_id: int,
    principal: Principal = Depends(require_permission("reimb.claim.read")),
    session: AsyncSession = Depends(get_session),
):
    claim = await get_claim(session, claim_id)
    if not await can_read_claim(
        session, actor_user_id=principal.user_id, claim=claim
    ):
        # Same slug as every other read path — no owner-vs-scope leak.
        raise errors.not_claim_owner()

    history = (
        (
            await session.execute(
                select(ReimbStatusHistory)
                .where(ReimbStatusHistory.claim_id == claim.id)
                .order_by(ReimbStatusHistory.id)
            )
        )
        .scalars()
        .all()
    )
    return_events = (
        (
            await session.execute(
                select(ReimbReturnEvent)
                .where(ReimbReturnEvent.claim_id == claim.id)
                .order_by(ReimbReturnEvent.id)
            )
        )
        .scalars()
        .all()
    )

    vocab = st.vocabulary(claim.kind)
    return_rows = [h for h in history if h.to_status in _RETURN_STATUSES]
    paired: dict[int, ReimbReturnEvent] = {}
    if len(return_rows) == len(return_events):
        paired = {h.id: e for h, e in zip(return_rows, return_events)}

    wanted_reason_ids = {
        int(rid) for e in paired.values() for rid in (e.reason_ids or [])
    }
    catalog: dict[int, ReturnReasonOut] = {}
    if wanted_reason_ids:
        rows = (
            (
                await session.execute(
                    select(ReimbReturnReasonCatalog)
                    .where(ReimbReturnReasonCatalog.id.in_(wanted_reason_ids))
                    .execution_options(include_deleted=True)
                )
            )
            .scalars()
            .all()
        )
        catalog = {row.id: _reason_out(row) for row in rows}

    names = await _actor_names(
        session, {h.actor_id for h in history if h.actor_id is not None}
    )

    out: list[TimelineEventOut] = []
    for row in history:
        event = paired.get(row.id)
        reasons = (
            [
                catalog[int(rid)]
                for rid in (event.reason_ids or [])
                if int(rid) in catalog
            ]
            if event is not None
            else []
        )
        out.append(
            TimelineEventOut(
                id=row.id,
                from_status=row.from_status,
                from_status_label=(
                    vocab.labels.get(row.from_status, row.from_status)
                    if row.from_status
                    else None
                ),
                to_status=row.to_status,
                to_status_label=vocab.labels.get(row.to_status, row.to_status),
                actor_display=(
                    names.get(row.actor_id) if row.actor_id is not None else None
                ),
                note=row.note,
                reasons=reasons,
                created_at=row.created_at,
            )
        )
    return out


@router.get("/return-reasons", response_model=list[ReturnReasonOut])
async def list_return_reasons(
    _: Principal = Depends(require_permission("reimb.claim.read")),
    session: AsyncSession = Depends(get_session),
):
    """The live taxonomy for the return dialog's chips.

    Ordered by ``category, code`` — the catalog has no ``sort`` column (unlike
    ``reimb_checklist_catalogs``). ``category`` is a PG ENUM, so Postgres sorts
    it by DECLARATION order, which is the authored taxonomy order
    (missing_doc → … → other): the chips land grouped and most-common-first
    without a sort column existing. Recorded in the module delta register."""
    rows = (
        (
            await session.execute(
                select(ReimbReturnReasonCatalog)
                .where(ReimbReturnReasonCatalog.is_active.is_(True))
                .order_by(
                    ReimbReturnReasonCatalog.category,
                    ReimbReturnReasonCatalog.code,
                )
            )
        )
        .scalars()
        .all()
    )
    return [_reason_out(row) for row in rows]
