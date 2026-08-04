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
from office_connect.core.models import User
from office_connect.core.time import utc_now
from office_connect.modules.reimbursement.api.deps import holder_names, work_item
from office_connect.modules.reimbursement.api.schemas import MyWorkOut
from office_connect.modules.reimbursement.models import ReimbClaim
from office_connect.modules.reimbursement.services import actions
from office_connect.modules.reimbursement.services import status as st

router = APIRouter()

_LIST_CAP = 100  # hard cap; the pagination envelope is a Stage-D deferral


#: The row mapper and the two batched name lookups moved to ``api/deps.py`` at
#: R-7-queue, when the oversight queue became their second caller. They are
#: shared mappers, not this router's privates.


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
                    ReimbClaim.status.not_in(st.ALL_TERMINAL_STATES),
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
                            ReimbClaim.status.not_in(st.ALL_TERMINAL_STATES),
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

    names = await holder_names(session, [*waiting, *in_flight])
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
            work_item(c, holder_display=_display(c), now=now, sla_due_at=_sla(c))
            for c in waiting
        ],
        in_flight=[
            work_item(c, holder_display=_display(c), now=now, sla_due_at=_sla(c))
            for c in in_flight
        ],
    )
