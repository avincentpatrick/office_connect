"""Shared helpers for the reimbursement routers — lookups, authorization,
and the one ``ClaimDetail`` mapper.

Read-scoping doctrine (spec §3.2 — claims are NOT bureau-public): the route's
coarse ``require_permission("reimb.claim.read")`` cannot scope reads because
the ``staff`` role's read grant is GLOBAL. ``can_read_claim`` adds the real
rule: the owner, or an actor whose *approve/review/fms_update* grant covers
the claim's org unit via ``authorize_scoped``.

Display lookups (claimant/org names, holder) read with ``include_deleted`` —
historical claims must keep rendering after a staff offboarding soft-delete.
Everything here is read-only; the routers own the commit.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.models import OrgUnit, Staff, User, WorkflowInstance
from office_connect.core.money import money_str
from office_connect.core.org_units import authorize_scoped
from office_connect.modules.reimbursement.api.schemas import (
    ClaimantOut,
    ClaimDetail,
    LegOut,
    OrgUnitRef,
)
from office_connect.modules.reimbursement.models import (
    ReimbClaim,
    ReimbItineraryLeg,
)
from office_connect.modules.reimbursement.services import errors
from office_connect.modules.reimbursement.services import status as st

_SCOPED_READ_PERMS = (
    "reimb.claim.approve",
    "reimb.claim.review",
    "reimb.claim.fms_update",
)


async def get_claim(session: AsyncSession, claim_id: int) -> ReimbClaim:
    """The live claim or 404 (the global soft-delete filter applies)."""
    claim = (
        await session.execute(select(ReimbClaim).where(ReimbClaim.id == claim_id))
    ).scalar_one_or_none()
    if claim is None:
        raise errors.claim_not_found()
    return claim


async def _display_staff(session: AsyncSession, staff_id: int) -> Staff | None:
    return (
        await session.execute(
            select(Staff)
            .where(Staff.id == staff_id)
            .execution_options(include_deleted=True)
        )
    ).scalar_one_or_none()


async def claim_org_unit(session: AsyncSession, claim: ReimbClaim) -> int | None:
    """The claim's authorization scope: the instance's org unit once submitted,
    else the claimant's section/division (the same derivation submit uses)."""
    if claim.workflow_instance_id is not None:
        instance = await session.get(WorkflowInstance, claim.workflow_instance_id)
        if instance is not None:
            return instance.org_unit_id
    staff = await _display_staff(session, claim.claimant_id)
    return (staff.section_id or staff.division_id) if staff else None


async def can_read_claim(
    session: AsyncSession, *, actor_user_id: int, claim: ReimbClaim
) -> bool:
    actor = await session.get(User, actor_user_id)
    if actor is not None and actor.staff_id == claim.claimant_id:
        return True
    org_unit_id = await claim_org_unit(session, claim)
    if org_unit_id is None:
        return False
    for perm in _SCOPED_READ_PERMS:
        if await authorize_scoped(session, actor_user_id, perm, org_unit_id):
            return True
    return False


async def holder_display(
    session: AsyncSession, *, holder_kind: str | None, holder_id: int | None
) -> str | None:
    """A render-ready holder name: the holder's staff full name (falling back
    to the login email), or "FMS" for the external leg."""
    if holder_kind == "external_fms":
        return "FMS"
    if holder_kind != "user" or holder_id is None:
        return None
    user = await session.get(User, holder_id)
    if user is None:
        return None
    if user.staff_id is not None:
        staff = await _display_staff(session, user.staff_id)
        if staff is not None and staff.full_name:
            return staff.full_name
    return user.email


async def _claimant_block(session: AsyncSession, claim: ReimbClaim) -> ClaimantOut:
    staff = await _display_staff(session, claim.claimant_id)
    if staff is None:
        # FK guarantees existence; a vanished row would be schema corruption.
        return ClaimantOut(staff_id=claim.claimant_id)

    unit_ids = [u for u in (staff.division_id, staff.section_id) if u is not None]
    units: dict[int, OrgUnit] = {}
    if unit_ids:
        rows = (
            await session.execute(
                select(OrgUnit)
                .where(OrgUnit.id.in_(unit_ids))
                .execution_options(include_deleted=True)
            )
        ).scalars()
        units = {u.id: u for u in rows}

    def _ref(unit_id: int | None) -> OrgUnitRef | None:
        unit = units.get(unit_id) if unit_id is not None else None
        return OrgUnitRef(id=unit.id, name=unit.name) if unit else None

    return ClaimantOut(
        staff_id=staff.id,
        employee_no=staff.employee_no,
        full_name=staff.full_name,
        position_title=staff.position_title,
        employment_status=staff.employment_status,
        division=_ref(staff.division_id),
        section=_ref(staff.section_id),
    )


def _leg_out(leg: ReimbItineraryLeg) -> LegOut:
    return LegOut(
        id=leg.id,
        seq=leg.seq,
        leg_date=leg.leg_date,
        place=leg.place,
        destination_region_code=leg.destination_region_code,
        time_depart=leg.time_depart,
        time_arrive=leg.time_arrive,
        transport_mode=leg.transport_mode,
        fare=money_str(leg.fare) if leg.fare is not None else None,
        per_diem_pct=leg.per_diem_pct,
        per_diem_amount=(
            money_str(leg.per_diem_amount)
            if leg.per_diem_amount is not None
            else None
        ),
        leg_total=money_str(leg.leg_total) if leg.leg_total is not None else None,
        lodging_provided=leg.lodging_provided,
        meals_provided=leg.meals_provided,
    )


async def claim_detail(session: AsyncSession, claim: ReimbClaim) -> ClaimDetail:
    """The one response mapper. Build BEFORE the router commits — the pydantic
    model holds plain values, so post-commit attribute expiry can't bite."""
    status_code = claim.status or st.DRAFT
    legs = (
        (
            await session.execute(
                select(ReimbItineraryLeg)
                .where(ReimbItineraryLeg.claim_id == claim.id)
                .order_by(ReimbItineraryLeg.seq, ReimbItineraryLeg.id)
            )
        )
        .scalars()
        .all()
    )
    return ClaimDetail(
        id=claim.id,
        ref_no=claim.ref_no,
        kind=claim.kind,
        status=status_code,
        status_label=st.STATUS_LABELS.get(status_code, status_code),
        next_action=claim.next_action or st.NEXT_ACTION.get(status_code),
        holder_kind=claim.holder_kind,
        holder_display=await holder_display(
            session, holder_kind=claim.holder_kind, holder_id=claim.holder_id
        ),
        holder_since=claim.holder_since,
        claimant=await _claimant_block(session, claim),
        is_jo_cos=claim.is_jo_cos,
        activity_id=claim.activity_id,
        dpo_no=claim.dpo_no,
        dpo_date=claim.dpo_date,
        purpose=claim.purpose,
        destination=claim.destination,
        destination_region_code=claim.destination_region_code,
        date_depart=claim.date_depart,
        date_return=claim.date_return,
        is_within_50km=claim.is_within_50km,
        overnight_stay=claim.overnight_stay,
        fund_source=claim.fund_source,
        other_total=money_str(claim.other_total),
        totals=claim.totals if claim.totals else None,
        legs=[_leg_out(leg) for leg in legs],
        created_at=claim.created_at,
        updated_at=claim.updated_at,
    )
