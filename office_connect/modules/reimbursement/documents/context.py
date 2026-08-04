"""Render context for the module's generated forms (R-5).

Deliberately a **separate contract** from ``services/checklist_facts.py``, even
though the two read overlapping rows. Facts feed the rule grammar: they are
referenced by name from admin-editable JSONB, so renaming a key is a catalog
migration. Context feeds a printed page: it is referenced only by templates in
this repository, and it carries display-shaped values (formatted names, resolved
org units, ordered leg rows) that a rule engine has no use for. Fusing them would
make every print tweak a change to the contract that seeded rules depend on.

**Money is never computed here.** Every figure is lifted from the
``reimb_claims.totals`` JSONB snapshot that ``services/compute.py`` wrote — the
module's single money-computation entry point. The template then formats it and
nothing more. This is the print-side application of the standing rule that the
server computes and the display layer displays; a Disbursement Voucher whose
total was recalculated at render time could disagree with the total the approver
saw, which is the precise failure the rule exists to prevent.

A claim whose ``totals`` is empty cannot be rendered. That is not an edge case to
paper over: ``services/drafts.py`` clears ``totals`` whenever a compute input
changes, so an empty snapshot means "the numbers are mid-edit". Rendering zeros
would produce an official-looking voucher for ₱0.00.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.models import OrgUnit, Staff, TenantConfig
from office_connect.core.money import money_str
from office_connect.core.time import utc_now
from office_connect.modules.reimbursement.models import (
    ReimbClaim,
    ReimbItineraryLeg,
)
from office_connect.modules.reimbursement.services import errors

# Bumped when the context SHAPE changes in a way that should invalidate existing
# snapshots. It is part of the fingerprint, so raising it re-renders every
# document on next generation — which is what you want after fixing a template
# that printed the wrong field.
CONTEXT_VERSION = 1

# Claim statuses in which the claimant is still editing. A document generated in
# one of these is a draft: it has no reference number and must not be mistaken
# for a filed original.
DRAFT_STATUSES = frozenset({"draft", "returned"})


def is_draft_claim(claim: ReimbClaim) -> bool:
    """Draft-ness is DERIVED from claim state, never passed in by a caller.

    This is what makes the Celery task safe to retry: a job queued while the
    claim was a draft and executed a second after submit produces the official
    document, not a stale draft, because it re-reads the claim.
    """
    return claim.status in DRAFT_STATUSES or claim.ref_no is None


async def _claimant(session: AsyncSession, claim: ReimbClaim) -> dict[str, Any]:
    staff = (
        await session.execute(
            select(Staff)
            .where(Staff.id == claim.claimant_id)
            .execution_options(include_deleted=True)
        )
    ).scalar_one_or_none()
    if staff is None:  # FK guarantees existence; absence is schema corruption
        return {
            "staff_id": claim.claimant_id,
            "full_name": "—",
            "employee_no": None,
            "position_title": None,
            "employment_status": None,
            "division": None,
            "section": None,
        }

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

    def _name(unit_id: int | None) -> str | None:
        unit = units.get(unit_id) if unit_id is not None else None
        return unit.name if unit else None

    return {
        "staff_id": staff.id,
        "full_name": staff.full_name,
        "employee_no": staff.employee_no,
        "position_title": staff.position_title,
        "employment_status": staff.employment_status,
        "division": _name(staff.division_id),
        "section": _name(staff.section_id),
    }


async def _tenant(session: AsyncSession) -> tuple[str, dict[str, Any]]:
    """The agency name printed on every form, plus its branding token overrides."""
    row = (
        await session.execute(select(TenantConfig).order_by(TenantConfig.id).limit(1))
    ).scalar_one_or_none()
    if row is None:
        return ("", {})
    return (row.name or "", row.branding or {})


def _legs(legs: list[ReimbItineraryLeg]) -> list[dict[str, Any]]:
    return [
        {
            "seq": leg.seq,
            "leg_date": leg.leg_date.isoformat() if leg.leg_date else None,
            "place": leg.place,
            "destination_region_code": leg.destination_region_code,
            "time_depart": leg.time_depart,
            "time_arrive": leg.time_arrive,
            "transport_mode": leg.transport_mode,
            "fare": money_str(leg.fare) if leg.fare is not None else None,
            "per_diem_pct": leg.per_diem_pct,
            "per_diem_amount": (
                money_str(leg.per_diem_amount)
                if leg.per_diem_amount is not None
                else None
            ),
            "leg_total": (
                money_str(leg.leg_total) if leg.leg_total is not None else None
            ),
            "lodging_provided": bool(leg.lodging_provided),
            "meals_provided": bool(leg.meals_provided),
        }
        for leg in legs
    ]


async def build_document_context(
    session: AsyncSession,
    *,
    claim: ReimbClaim,
    document_key: str,
    title: str,
    form_no: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """The full render context for one document.

    Raises ``reimb_totals_missing`` when the money snapshot is absent — see the
    module docstring for why that is a refusal rather than a default.
    """
    totals = claim.totals or {}
    if not totals.get("grand"):
        raise errors.totals_missing()

    stamp = now or utc_now()
    agency, branding = await _tenant(session)

    legs = list(
        (
            await session.execute(
                select(ReimbItineraryLeg)
                .where(ReimbItineraryLeg.claim_id == claim.id)
                .order_by(ReimbItineraryLeg.seq)
            )
        )
        .scalars()
        .all()
    )

    draft = is_draft_claim(claim)

    return {
        # The envelope core's base template always renders. `generated_at` is
        # ISO-8601 rather than a datetime so the context stays JSON-canonical —
        # it is hashed into the fingerprint.
        "doc": {
            "key": document_key,
            "title": title,
            "form_no": form_no,
            "agency": agency,
            "ref_no": claim.ref_no,
            "is_draft": draft,
            "generated_at": stamp.isoformat(),
            "context_version": CONTEXT_VERSION,
        },
        "claim": {
            "id": claim.id,
            "ref_no": claim.ref_no,
            "kind": claim.kind,
            "status": claim.status,
            "dpo_no": claim.dpo_no,
            "dpo_date": claim.dpo_date.isoformat() if claim.dpo_date else None,
            "purpose": claim.purpose,
            "destination": claim.destination,
            "destination_region_code": claim.destination_region_code,
            "date_depart": (
                claim.date_depart.isoformat() if claim.date_depart else None
            ),
            "date_return": (
                claim.date_return.isoformat() if claim.date_return else None
            ),
            "fund_source": claim.fund_source,
            "is_jo_cos": bool(claim.is_jo_cos),
            "is_within_50km": bool(claim.is_within_50km),
            "overnight_stay": bool(claim.overnight_stay),
        },
        "claimant": await _claimant(session, claim),
        "legs": _legs(legs),
        # Server-computed, verbatim. The template formats; it never arithmetics.
        "totals": {
            "per_diem": totals.get("per_diem"),
            "transport": totals.get("transport"),
            "other": money_str(claim.other_total or 0),
            "grand": totals.get("grand"),
            "advance": totals.get("advance"),
            "to_reimburse": totals.get("to_reimburse"),
            "to_refund": totals.get("to_refund"),
            "days": totals.get("days") or [],
        },
        # Not part of the printed page; carried so the fingerprint changes when
        # the branding that styles the PDF changes.
        "branding": branding,
    }
