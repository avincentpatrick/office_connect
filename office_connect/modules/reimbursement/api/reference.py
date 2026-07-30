"""Reference data for the wizard's pickers.

``GET /regions`` serves the PSGC-region → EO 77 cluster options for the Trip
and Itinerary steps (one row per region: the latest row effective as of Manila
today). Transport modes are a closed enum mirrored by the FE and enforced by
the request schemas' ``Literal`` — no endpoint needed (recorded in the module
doc). Return-reason taxonomy ships with the return dialog (deferred).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.auth.dependencies import require_permission
from office_connect.core.auth.principal import Principal
from office_connect.core.db import get_session
from office_connect.core.time import to_manila, utc_now
from office_connect.modules.reimbursement.api.schemas import RegionOut
from office_connect.modules.reimbursement.models import ReimbRegionCluster

router = APIRouter()


@router.get("/regions", response_model=list[RegionOut])
async def list_regions(
    _: Principal = Depends(require_permission("reimb.claim.read")),
    session: AsyncSession = Depends(get_session),
):
    today = to_manila(utc_now()).date()
    rows = (
        (
            await session.execute(
                select(ReimbRegionCluster)
                .where(
                    ReimbRegionCluster.is_active.is_(True),
                    ReimbRegionCluster.effective_from <= today,
                )
                .order_by(
                    ReimbRegionCluster.region_code,
                    ReimbRegionCluster.effective_from.desc(),
                )
            )
        )
        .scalars()
        .all()
    )
    latest: dict[str, ReimbRegionCluster] = {}
    for row in rows:  # first per code wins = latest effective (order above)
        latest.setdefault(row.region_code, row)
    return [
        RegionOut(
            region_code=row.region_code,
            region_name=row.region_name,
            cluster=row.cluster,
        )
        for row in latest.values()
    ]
