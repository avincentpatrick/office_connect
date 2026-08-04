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

from office_connect.core.documents import find_active
from office_connect.core.models import Attachment, OrgUnit, Staff, User, WorkflowInstance
from office_connect.core.money import money_str
from office_connect.core.org_units import authorize_scoped
from office_connect.modules.reimbursement.api.schemas import (
    ChecklistBlockerOut,
    ChecklistFileOut,
    ChecklistFlagOut,
    ChecklistItemOut,
    ChecklistOut,
    ChecklistSummaryOut,
    ClaimantOut,
    ClaimDetail,
    LegOut,
    OrgUnitRef,
    PacketOut,
)
# The registry module, not the package: all this layer needs is the key, and a
# package import would drag the generator (and its checklist dependency) into
# every request that reads a claim.
from office_connect.modules.reimbursement.documents.registry import PACKET
from office_connect.modules.reimbursement.models import (
    ReimbClaim,
    ReimbItineraryLeg,
)
from office_connect.modules.reimbursement.services import actions, checklist, errors
from office_connect.modules.reimbursement.services import attachments as evidence
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
    return await has_scoped_grant(
        session, actor_user_id=actor_user_id, claim=claim, permissions=_SCOPED_READ_PERMS
    )


async def has_scoped_grant(
    session: AsyncSession,
    *,
    actor_user_id: int,
    claim: ReimbClaim,
    permissions: tuple[str, ...],
) -> bool:
    """Does any of ``permissions`` cover this claim's org unit?

    Extracted from ``can_read_claim`` at R-5-packet so the generate endpoint can
    ask the narrower question — "may this actor act on this claim's paperwork?"
    — without re-deriving the org unit. Ownership is deliberately NOT folded in:
    the two callers disagree about whether the owner qualifies, and a helper
    that quietly answered both would hide that.
    """
    org_unit_id = await claim_org_unit(session, claim)
    if org_unit_id is None:
        return False
    for perm in permissions:
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


# --- R-3: the documentary packet -------------------------------------------

#: Why an item applies, in the claimant's language. The grammar hands back a
#: machine slug; turning it into prose is a display concern, and it lives here
#: (not in core) because only the module knows what its own facts MEAN.
_RULE_PROSE = {
    "condition_met": "Required because of what you entered on this claim.",
    "any_satisfied": "Required because of what you entered on this claim.",
    "all_satisfied": "Required because of what you entered on this claim.",
}


def _blocker_out(item) -> ChecklistBlockerOut:
    return ChecklistBlockerOut(
        catalog_id=item.catalog_id,
        item_id=item.item_id,
        code=item.code,
        label=item.label,
        group=item.group,
        evidence=item.evidence,
        reason=item.reason,
    )


def checklist_summary_out(
    status, *, catalog_labels: dict[int, tuple[str, str]] | None = None
) -> ChecklistSummaryOut:
    """Map the engine's ``PacketStatus`` onto the wire.

    ``gate_message`` is built from the SAME error factory the refused submit
    raises, so the sentence the Review step shows before you press the button
    and the sentence the 422 carries afterwards are literally one string
    (ui-standards §3.14 — the client authors no gate wording at all).
    """
    labels = catalog_labels or {}
    return ChecklistSummaryOut(
        required_total=status.required_total,
        required_done=status.required_done,
        complete=status.complete,
        blocking=[_blocker_out(item) for item in status.blocking],
        flags=[
            ChecklistFlagOut(
                catalog_id=catalog_id,
                code=labels.get(catalog_id, ("", ""))[0],
                label=labels.get(catalog_id, ("", ""))[1],
                check_type=check.type,
                reason=check.reason,
                message=check.message,
                detail=dict(check.detail),
                remedy=check.remedy,
            )
            for catalog_id, check in status.flags
        ],
        gate_message=(
            None
            if status.complete
            else errors.packet_incomplete(status.blocking).message
        ),
    )


def checklist_out(view: checklist.ChecklistView) -> ChecklistOut:
    """The Documents step's payload — rows plus the gate over them."""
    labels = {
        row.plan.catalog.catalog_id: (row.plan.catalog.code, row.plan.catalog.label)
        for row in view.rows
    }
    return ChecklistOut(
        items=[
            ChecklistItemOut(
                catalog_id=row.plan.catalog.catalog_id,
                item_id=row.item_id,
                code=row.plan.catalog.code,
                label=row.plan.catalog.label,
                group=row.plan.catalog.group,
                evidence=row.plan.catalog.evidence,
                required=row.plan.required,
                required_because=_RULE_PROSE.get(row.plan.rule_reason),
                status=row.plan.derived_status,
                flag_reason=(
                    " ".join(check.message for check in row.plan.flags) or None
                ),
                waiver_reason=row.waiver_reason,
                sort=row.plan.catalog.sort,
                files=[ChecklistFileOut(**file) for file in row.files],
            )
            for row in view.rows
        ],
        summary=checklist_summary_out(view.status, catalog_labels=labels),
    )


async def claim_checklist_summary(
    session: AsyncSession, claim: ReimbClaim
) -> ChecklistSummaryOut:
    """The summary embedded on ``ClaimDetail``. Read-only — never materializes."""
    view = await checklist.checklist_view(session, claim=claim)
    return checklist_out(view).summary


async def claim_packet(session: AsyncSession, claim: ReimbClaim) -> PacketOut | None:
    """The live combined packet, or ``None`` (spec §9.2 preview — R-5-packet).

    One indexed lookup on the ACTIVE snapshot: a voided or superseded copy must
    never be offered, because the whole point of voiding is that the document no
    longer describes the claim.

    No new download route. Core's ``/api/v1/attachments/{id}/content`` is already
    scoped to this claim by the holder authorizer ``services/attachments.py``
    registers, and already serves a generated PDF ``inline`` (api-standards
    §9c) — which is the only reason the frame can render it at all.
    """
    snapshot = await find_active(
        session,
        subject_kind=evidence.HOLDER_KIND,
        subject_id=claim.id,
        document_key=PACKET,
    )
    if snapshot is None:
        return None

    # A snapshot whose attachment vanished is schema corruption, not a state to
    # render: offering a link to a row that is gone would 404 in a frame with no
    # explanation. Report "no packet" instead.
    attachment = await session.get(Attachment, snapshot.attachment_id)
    if attachment is None or attachment.deleted_at is not None:
        return None

    return PacketOut(
        attachment_id=attachment.id,
        download_path=f"/api/v1/attachments/{attachment.id}/content",
        generated_at=snapshot.generated_at,
        is_draft=snapshot.is_draft,
        content_sha256=snapshot.content_sha256,
        source_fingerprint=snapshot.source_fingerprint,
    )


async def claim_detail(
    session: AsyncSession, claim: ReimbClaim, *, actor_user_id: int
) -> ClaimDetail:
    """The one response mapper. Build BEFORE the router commits — the pydantic
    model holds plain values, so post-commit attribute expiry can't bite.

    ``actor_user_id`` is required because the action set is per-actor: the same
    claim shows Approve/Return to its gate holder and nothing to a bystander
    (workflow-standards §3)."""
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
    sla_due_at, sla_state = await actions.claim_sla(session, claim=claim)
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
        available_actions=await actions.claim_actions(
            session, claim=claim, actor_user_id=actor_user_id
        ),
        row_version=await actions.instance_row_version(session, claim),
        sla_due_at=sla_due_at,
        sla_state=sla_state,
        checklist=await claim_checklist_summary(session, claim),
        packet=await claim_packet(session, claim),
        created_at=claim.created_at,
        updated_at=claim.updated_at,
    )
