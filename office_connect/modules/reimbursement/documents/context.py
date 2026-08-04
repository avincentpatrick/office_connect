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

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.models import (
    Attachment,
    OrgUnit,
    Staff,
    TenantConfig,
    User,
    WorkflowEvent,
    WorkflowState,
)
from office_connect.core.money import money_str
from office_connect.core.time import utc_now
from office_connect.modules.reimbursement.documents.registry import (
    BODY_PARTIALS,
    PACKET,
    PACKET_TITLE,
)
from office_connect.modules.reimbursement.models import (
    ReimbAttachment,
    ReimbCashAdvance,
    ReimbClaim,
    ReimbItineraryLeg,
)
from office_connect.modules.reimbursement.services import checklist, errors
from office_connect.modules.reimbursement.services import status as st

# Bumped when the context SHAPE changes in a way that should invalidate existing
# snapshots. It is part of the fingerprint, so raising it re-renders every
# document on next generation — which is what you want after fixing a template
# that printed the wrong field.
#
# It is a DECLARATION, not the invalidation mechanism: adding a key already
# moves every fingerprint on its own, so a bump is strictly redundant for
# correctness. Bump it anyway when the shape moves — a session that changes the
# shape and leaves this alone teaches the next one that the constant is
# decorative, and the next shape change may be one the keys alone do not
# announce (a rename, a value re-typed).
#
# v2 (R-6-liq-settle): the `advance`, `settlement` and `certifications` blocks.
CONTEXT_VERSION = 2

#: Print-side nouns for the packet cover's money block. Two kinds, one table: a
#: liquidation reports what was SPENT against an advance, a reimbursement what
#: is CLAIMED. Same figures, different sentence — and a sentence is prose, which
#: lives beside GROUP_LABELS rather than in a second copy of the markup. Forking
#: the table behind `{% if claim.kind %}` would duplicate 38 lines of money
#: rendering and guarantee the two copies drift.
#:
#: The single-kind FORMS (`_dv32_body`, `_lr44_body`) keep their own hard-coded
#: nouns: indirecting a label that can only ever say one thing buys nothing.
MONEY_LABELS = {
    "reimbursement": {
        "heading": "Amount claimed",
        "total": "Total claim",
        "refundable": "Amount refundable",
        "payable": "Amount due the payee",
    },
    "liquidation": {
        "heading": "Settlement of the cash advance",
        "total": "Total amount spent",
        "refundable": "Excess cash advance — refundable",
        "payable": "Amount reimbursable to the accountable officer",
    },
}

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


#: The three R-6-liq-settle blocks, empty. Every context carries them, ALWAYS —
#: a reimbursement claim gets these all-None copies rather than no key at all.
#:
#: Three reasons, and the first is sufficient on its own: the environment runs
#: `StrictUndefined`, the packet resolves `{% include section.body %}` at render
#: time, and `_lr44_body.html.j2` is reachable from any context (a test already
#: renders every BODY_PARTIALS entry against a reimbursement claim). A key that
#: appears only for liquidations would raise `UndefinedError` inside a
#: `RenderFailed` — a SILENT `outcome="failed"` in the worker. Second: a context
#: whose key set varies per row is not a versioned shape, which is what
#: CONTEXT_VERSION claims to describe. Third: the all-None copy is what makes
#: that existing test a free regression guard instead of a special case.
_NO_ADVANCE: dict[str, Any] = {
    "id": None,
    "dv_no": None,
    "dv_date": None,
    "amount": None,
    "date_return": None,
    "deadline_date": None,
    "status": None,
}
_NO_SETTLEMENT: dict[str, Any] = {
    "mode": None,
    "or_no": None,
    "or_date": None,
    "refund_amount": None,
    "settled_at": None,
    "spawned_claim_ref": None,
}
_NO_CERTIFICATIONS: dict[str, Any] = {
    "a": {"name": None, "recorded_at": None},
    "b": {"name": None, "recorded_at": None},
    "c": {"recorded_by": None, "recorded_at": None, "note": None},
}


async def _advance_and_settlement(
    session: AsyncSession, claim: ReimbClaim
) -> tuple[dict[str, Any], dict[str, Any]]:
    """The cash advance this liquidation answers, and how it settled.

    Kept as TWO blocks, not one. The advance is a fact from the moment the
    liquidation is created; the settlement is a fact only at the end. Merged,
    a half-populated block's emptiness would mean two different things and no
    template could tell "no advance" from "not settled yet".

    ``totals.advance`` already carries the AMOUNT — but only the amount, because
    ``compute`` reads the row and keeps nothing else. GAM App 44's central line
    is *"Amount of cash advance per DV No. ___ dated ___"*, which is unprintable
    without this.

    Dates go out as ISO strings: the context is hashed through
    ``canonical_json``, and a ``date`` object is not JSON.
    """
    if claim.kind != st.LIQUIDATION_KIND or claim.cash_advance_id is None:
        return (dict(_NO_ADVANCE), dict(_NO_SETTLEMENT))

    row = (
        await session.execute(
            select(ReimbCashAdvance)
            .where(ReimbCashAdvance.id == claim.cash_advance_id)
            .execution_options(include_deleted=True)
        )
    ).scalar_one_or_none()
    if row is None:
        return (dict(_NO_ADVANCE), dict(_NO_SETTLEMENT))

    spawn_ref = (
        await session.execute(
            select(ReimbClaim.ref_no).where(
                ReimbClaim.spawned_from_claim_id == claim.id,
                ReimbClaim.status.is_not(None),
                ReimbClaim.status != st.CANCELLED,
                ReimbClaim.ref_no.is_not(None),
            )
        )
    ).scalars().first()

    advance = {
        "id": row.id,
        "dv_no": row.dv_no,
        "dv_date": row.dv_date.isoformat() if row.dv_date else None,
        "amount": money_str(row.amount) if row.amount is not None else None,
        "date_return": row.date_return.isoformat() if row.date_return else None,
        "deadline_date": (
            row.deadline_date.isoformat() if row.deadline_date else None
        ),
        "status": row.status,
    }
    settlement = {
        "mode": row.settlement_mode,
        "or_no": row.refund_or_no,
        "or_date": row.refund_or_date.isoformat() if row.refund_or_date else None,
        "refund_amount": (
            money_str(row.refund_amount) if row.refund_amount is not None else None
        ),
        "settled_at": row.settled_at.isoformat() if row.settled_at else None,
        "spawned_claim_ref": spawn_ref,
    }
    return (advance, settlement)


async def _certifications(
    session: AsyncSession, claim: ReimbClaim
) -> dict[str, Any]:
    """Who the platform RECORDED at each certification, if anyone.

    Read from the engine's append-only event log, which is the authoritative
    history. What each entry is allowed to assert on the printed page is a
    template question and is argued in ``_lr44_body.html.j2`` — the short
    version is that B may be REPORTED beneath a blank signature line and C may
    never be, because for C the platform holds the name of the Admin Officer who
    recorded the signature, not the Head of Accounting who gave it.
    """
    if claim.kind != st.LIQUIDATION_KIND or claim.workflow_instance_id is None:
        return {key: dict(value) for key, value in _NO_CERTIFICATIONS.items()}

    rows = (
        await session.execute(
            select(
                WorkflowEvent.action,
                WorkflowState.code,
                WorkflowEvent.actor_user_id,
                WorkflowEvent.created_at,
                WorkflowEvent.comment,
            )
            .join(
                WorkflowState,
                WorkflowState.id == WorkflowEvent.from_state_id,
                isouter=True,
            )
            .where(WorkflowEvent.instance_id == claim.workflow_instance_id)
            .order_by(WorkflowEvent.id)
        )
    ).all()

    found: dict[str, tuple[int | None, datetime, str | None]] = {}
    for action, from_code, actor_id, created_at, comment in rows:
        if action == "submit":
            # Certification A has no gate — filing IS the certification (the
            # claimant is the maker). The submit event is its only record.
            found.setdefault("a", (actor_id, created_at, None))
        elif action == "approve" and from_code in (st.CERTIFY_B, st.CERTIFY_C):
            found["b" if from_code == st.CERTIFY_B else "c"] = (
                actor_id,
                created_at,
                comment,
            )

    names = await _actor_names(
        session, {actor for actor, _, _ in found.values() if actor is not None}
    )
    result = {key: dict(value) for key, value in _NO_CERTIFICATIONS.items()}
    for slot, (actor_id, created_at, comment) in found.items():
        who = names.get(actor_id) if actor_id is not None else None
        stamp = created_at.isoformat() if created_at else None
        if slot == "c":
            result["c"] = {
                "recorded_by": who,
                "recorded_at": stamp,
                "note": comment,
            }
        else:
            result[slot] = {"name": who, "recorded_at": stamp}
    return result


async def _actor_names(
    session: AsyncSession, user_ids: set[int]
) -> dict[int, str]:
    """One batched user→display-name lookup, ``include_deleted`` so a document
    keeps naming the right person after they are offboarded. Same shape as
    ``api/tracking.py::_actor_names``; duplicated rather than imported because
    the API layer must not become a dependency of the print layer."""
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
    advance, settlement = await _advance_and_settlement(session, claim)
    certifications = await _certifications(session, claim)

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
            # The COA 30-day clock this claim was measured against. A display
            # mirror of the advance's pinned deadline (cash_advance.link_claim
            # owns it) — and the Liquidation Report is the artifact that
            # evidences compliance with it.
            "liquidation_deadline": (
                claim.liquidation_deadline.isoformat()
                if claim.liquidation_deadline
                else None
            ),
        },
        "claimant": await _claimant(session, claim),
        "legs": _legs(legs),
        # The cash advance and how it settled (R-6-liq-settle). Present on every
        # context, all-None off the liquidation path — see the constants above.
        "advance": advance,
        "settlement": settlement,
        "certifications": certifications,
        # Per-kind print nouns for the packet cover's money block.
        "money_labels": MONEY_LABELS.get(
            claim.kind or "", MONEY_LABELS["reimbursement"]
        ),
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


# --------------------------------------------------------------------------
# The combined packet (R-5-packet)
# --------------------------------------------------------------------------

#: The 7 catalog groups in COA order — the declaration order of
#: ``models/enums.py::ChecklistGroup``, which is the order the circular lists
#: them in and therefore the order a packet is assembled in.
GROUP_ORDER = (
    "authority",
    "itinerary",
    "proof_of_travel",
    "transport",
    "lodging_meals",
    "report",
    "financial",
)

#: Print-side prose for the machine slugs. Lives here, not in core, for the same
#: reason ``api/deps.py::_RULE_PROSE`` does: only the module knows what its own
#: vocabulary means, and a printed page is a display surface like any other.
GROUP_LABELS = {
    "authority": "Authority to travel",
    "itinerary": "Itinerary",
    "proof_of_travel": "Proof of travel",
    "transport": "Transport",
    "lodging_meals": "Lodging and meals",
    "report": "Report",
    "financial": "Financial",
}

ITEM_STATUS_LABELS = {
    "missing": "Not attached",
    "attached": "Attached",
    "generated": "Generated by the system",
    "auto_passed": "Checked",
    "auto_flagged": "Flagged for review",
    "waived": "Waived",
}

EVIDENCE_LABELS = {
    "upload": "Attached by the claimant",
    "generated_doc": "Generated by the system",
    "external_wet_sign": "Signed by hand, then attached",
    "data_only": "Held as claim data — nothing to attach",
}

#: A quarantined file must be visible ON the manifest, not silently dropped: an
#: Accounting clerk counting envelopes needs to know a receipt was rejected, not
#: merely that it is absent.
SCAN_LABELS = {
    "pending": "Virus scan pending",
    "clean": "Scanned",
    "infected": "QUARANTINED — not usable",
    "error": "Scan unavailable",
}

CUSTODY_LABELS = {
    "scanned": "Scanned copy on file",
    "original_to_accounting": "Original sent to Accounting",
    "forwarded_to_coa": "Original forwarded to COA",
}


@dataclass(frozen=True)
class PacketSection:
    """One generated form as it appears inside the packet.

    Assembled by ``documents/service.py`` (which owns the bindings and knows
    what was rendered this pass) and handed here, so the context layer never
    queries ``reimb_template_maps`` and the two modules keep their one-way
    dependency.
    """

    document_key: str
    checklist_code: str
    title: str
    form_no: str | None
    #: The live snapshot's content hash, or None when that form has not been
    #: generated. Printed on the cover so the packet vouches for its parts.
    content_sha256: str | None = None


def _size_label(byte_size: int | None) -> str:
    """Bytes in a unit a person reads. Not money — no rounding rule applies."""
    if not byte_size:
        return "—"
    if byte_size < 1024:
        return f"{byte_size} B"
    if byte_size < 1024 * 1024:
        return f"{byte_size / 1024:.0f} KB"
    return f"{byte_size / (1024 * 1024):.1f} MB"


def _group_index(group: str) -> int:
    """Unknown groups sort last rather than raising — a catalog edit must never
    stop a packet printing."""
    return GROUP_ORDER.index(group) if group in GROUP_ORDER else len(GROUP_ORDER)


def _checklist_rows(view: checklist.ChecklistView) -> list[dict[str, Any]]:
    """The COA checklist as the Admin Officer's final-check sheet."""
    rows = [
        {
            "code": row.plan.catalog.code,
            "label": row.plan.catalog.label,
            "group": row.plan.catalog.group,
            "group_label": GROUP_LABELS.get(
                row.plan.catalog.group, row.plan.catalog.group
            ),
            "evidence": row.plan.catalog.evidence,
            "evidence_label": EVIDENCE_LABELS.get(
                row.plan.catalog.evidence, row.plan.catalog.evidence
            ),
            "required": bool(row.plan.required),
            "status": row.plan.derived_status,
            "status_label": ITEM_STATUS_LABELS.get(
                row.plan.derived_status, row.plan.derived_status
            ),
            "flagged": bool(row.plan.flags),
            "sort": row.plan.catalog.sort,
        }
        for row in view.rows
    ]
    return sorted(
        rows, key=lambda r: (_group_index(r["group"]), r["sort"], r["code"])
    )


async def _evidence_manifest(
    session: AsyncSession, *, claim: ReimbClaim, view: checklist.ChecklistView
) -> list[dict[str, Any]]:
    """Every file the claimant supplied, in COA checklist order.

    **A manifest, not a merge.** The packet lists what should be stapled behind
    it and vouches for each file by SHA-256; it does not reproduce the bytes.
    Two reasons, both load-bearing: COA takes delivery of the ORIGINAL receipts
    (which is why ``reimb_attachments.custody`` exists at all), so a printed
    scan is not the evidence anyway; and merging a claimant's upload into the
    packet would put bytes we did not author inside a document that is served
    ``inline`` precisely because we did author every byte of it
    (api-standards §9c).

    Uploads only. A generated PDF is not evidence a human supplied, and the
    packet already contains the generated forms in full.
    """
    catalogs = {
        row.item_id: row.plan.catalog for row in view.rows if row.item_id is not None
    }

    rows = (
        await session.execute(
            select(ReimbAttachment, Attachment)
            .join(Attachment, Attachment.id == ReimbAttachment.attachment_id)
            .where(
                ReimbAttachment.claim_id == claim.id,
                ReimbAttachment.checklist_item_id.is_not(None),
                Attachment.origin == "uploaded",
            )
            .order_by(ReimbAttachment.id)
        )
    ).all()

    ordered: list[tuple[tuple[int, int, str, int], dict[str, Any]]] = []
    for join, attachment in rows:
        catalog = catalogs.get(join.checklist_item_id)
        code = catalog.code if catalog else "—"
        sort_key = (
            _group_index(catalog.group) if catalog else len(GROUP_ORDER),
            catalog.sort if catalog else 0,
            code,
            join.id,
        )
        ordered.append(
            (
                sort_key,
                {
                    "code": code,
                    "label": catalog.label if catalog else "Unfiled attachment",
                    "group_label": (
                        GROUP_LABELS.get(catalog.group, catalog.group)
                        if catalog
                        else "Other"
                    ),
                    "filename": attachment.original_filename,
                    "size_label": _size_label(attachment.byte_size),
                    # The ORIGINAL bytes' hash, not the sanitized derivative's:
                    # this line is what lets an auditor prove the file in the
                    # envelope is the file the system received.
                    "sha256": attachment.sha256,
                    "scan_status": attachment.scan_status,
                    "scan_label": SCAN_LABELS.get(
                        attachment.scan_status, attachment.scan_status
                    ),
                    "custody_label": CUSTODY_LABELS.get(join.custody, join.custody),
                    "usable": attachment.scan_status != "infected",
                    # ISO-8601, never a datetime — the whole context is hashed
                    # through canonical_json.
                    "uploaded_at": (
                        join.created_at.isoformat() if join.created_at else None
                    ),
                },
            )
        )

    return [payload for _, payload in sorted(ordered, key=lambda pair: pair[0])]


async def build_packet_context(
    session: AsyncSession,
    *,
    claim: ReimbClaim,
    sections: list[PacketSection],
    title: str = PACKET_TITLE,
    now: datetime | None = None,
) -> dict[str, Any]:
    """The render context for the combined packet.

    Builds on ``build_document_context`` rather than beside it, so the money
    refusal, the claimant block and the draft derivation have exactly one
    implementation. What is added is the cover's contents list, the COA
    checklist and the evidence manifest.

    ``doc.fingerprint`` is deliberately absent here — the caller computes it
    over this context and injects it before rendering (see
    ``service.comparable_context``). A document cannot contain the hash of its
    own bytes, but it can carry the fingerprint of the data that produced it.
    """
    context = await build_document_context(
        session,
        claim=claim,
        document_key=PACKET,
        title=title,
        form_no=None,
        now=now,
    )

    view = await checklist.checklist_view(session, claim=claim, now=now)
    manifest = await _evidence_manifest(session, claim=claim, view=view)
    rows = _checklist_rows(view)

    context["packet"] = {
        "sections": [
            {
                "document_key": section.document_key,
                "checklist_code": section.checklist_code,
                "title": section.title,
                "form_no": section.form_no,
                "content_sha256": section.content_sha256,
                # Resolved from the code-side table, never from data — see
                # registry.BODY_PARTIALS. None means "listed but not embedded".
                "body": BODY_PARTIALS.get(section.document_key),
            }
            for section in sections
        ],
        "checklist": rows,
        "evidence": manifest,
        "counts": {
            "required_total": view.status.required_total,
            "required_done": view.status.required_done,
            "complete": view.status.complete,
            "evidence_files": len(manifest),
        },
    }
    return context
