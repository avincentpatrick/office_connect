"""My Work — the module's landing inbox (spec §7 rule 3).

Two self-keyed lists over the denormalized holder/status columns:
"waiting on you" (holder = my user, longest-waiting first) above "your claims
in flight" (claimant = my staff, excluding rows already in the first list).
Membership is holder/claimant-keyed, so no scope check is needed — nothing
another user holds or owns can appear (spec §3.2 stays server-side by
construction).

R-4-screens closed the SLA deferral: each row carries the active gate step's
``sla_due_at`` plus the spec §6.3 derived badge (``on_track``/``due_soon``/
``overdue``), server-computed in ``services/actions.py`` so the browser never
reasons about a Manila deadline. Ordering stays ``holder_since`` ASC — the
longest-waiting item is the most overdue one, so urgency floats up for free.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.auth.dependencies import require_permission
from office_connect.core.auth.principal import Principal
from office_connect.core.db import get_session
from office_connect.core.models import Staff, User
from office_connect.core.time import utc_now
from office_connect.modules.reimbursement.api.schemas import (
    MyWorkOut,
    WorkItemOut,
)
from office_connect.modules.reimbursement.models import ReimbClaim
from office_connect.modules.reimbursement.services import actions
from office_connect.modules.reimbursement.services import status as st

router = APIRouter()

_LIST_CAP = 100  # hard cap; the pagination envelope is a Stage-D deferral


def _work_item(
    claim: ReimbClaim,
    *,
    holder_display: str | None,
    now: datetime,
    sla_due_at: datetime | None = None,
) -> WorkItemOut:
    status_code = claim.status or st.DRAFT
    days = (
        max((now - claim.holder_since).days, 0)
        if claim.holder_since is not None
        else 0
    )
    totals = claim.totals or {}
    return WorkItemOut(
        id=claim.id,
        ref_no=claim.ref_no,
        purpose=claim.purpose,
        destination=claim.destination,
        status=status_code,
        status_label=st.STATUS_LABELS.get(status_code, status_code),
        next_action=claim.next_action or st.NEXT_ACTION.get(status_code),
        holder_kind=claim.holder_kind,
        holder_display=holder_display,
        holder_since=claim.holder_since,
        days_in_state=days,
        grand=totals.get("grand"),
        sla_due_at=sla_due_at,
        sla_state=actions.sla_state(sla_due_at, now=now),
        updated_at=claim.updated_at,
    )


async def _holder_names(
    session: AsyncSession, claims: list[ReimbClaim]
) -> dict[int, str]:
    """One batched user→staff-name lookup for every 'user' holder in the set."""
    user_ids = {
        c.holder_id
        for c in claims
        if c.holder_kind == "user" and c.holder_id is not None
    }
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


@router.get("/my-work", response_model=MyWorkOut)
async def my_work(
    principal: Principal = Depends(require_permission("reimb.claim.read")),
    session: AsyncSession = Depends(get_session),
):
    now = utc_now()

    waiting = (
        (
            await session.execute(
                select(ReimbClaim)
                .where(
                    ReimbClaim.holder_kind == "user",
                    ReimbClaim.holder_id == principal.user_id,
                    ReimbClaim.status.not_in(st.TERMINAL_STATES),
                )
                .order_by(
                    ReimbClaim.holder_since.asc().nulls_last(),
                    ReimbClaim.id.asc(),
                )
                .limit(_LIST_CAP)
            )
        )
        .scalars()
        .all()
    )

    actor = await session.get(User, principal.user_id)
    in_flight: list[ReimbClaim] = []
    if actor is not None and actor.staff_id is not None:
        in_flight = (
            (
                await session.execute(
                    select(ReimbClaim)
                    .where(
                        ReimbClaim.claimant_id == actor.staff_id,
                        or_(
                            ReimbClaim.status.is_(None),  # legacy pre-stamp rows
                            ReimbClaim.status.not_in(st.TERMINAL_STATES),
                        ),
                        # Exclude what the first list already shows (NULL-safe).
                        or_(
                            ReimbClaim.holder_kind.is_(None),
                            ReimbClaim.holder_kind != "user",
                            ReimbClaim.holder_id != principal.user_id,
                        ),
                    )
                    .order_by(ReimbClaim.updated_at.desc(), ReimbClaim.id.asc())
                    .limit(_LIST_CAP)
                )
            )
            .scalars()
            .all()
        )

    names = await _holder_names(session, [*waiting, *in_flight])
    # Spec §6.3's approver-facing badge: one batched join over the active gate
    # steps (the partial SLA index covers it), never a per-row query.
    due = await actions.active_step_due_dates(
        session,
        [
            c.workflow_instance_id
            for c in (*waiting, *in_flight)
            if c.workflow_instance_id is not None
        ],
    )

    def _sla(claim: ReimbClaim) -> datetime | None:
        if claim.workflow_instance_id is None:
            return None
        return due.get(claim.workflow_instance_id)

    def _display(claim: ReimbClaim) -> str | None:
        if claim.holder_kind == "external_fms":
            return "FMS"
        if claim.holder_kind == "user" and claim.holder_id is not None:
            if claim.holder_id == principal.user_id:
                return "You"
            return names.get(claim.holder_id)
        return None

    return MyWorkOut(
        waiting_on_you=[
            _work_item(c, holder_display=_display(c), now=now, sla_due_at=_sla(c))
            for c in waiting
        ],
        in_flight=[
            _work_item(c, holder_display=_display(c), now=now, sla_due_at=_sla(c))
            for c in in_flight
        ],
    )
