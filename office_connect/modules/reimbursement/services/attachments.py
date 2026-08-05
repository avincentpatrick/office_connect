"""Claim evidence — the module's seam onto core attachments (core-service #2).

Rule 10: the module never re-implements validation, magic-byte sniffing, hashing,
storage, scanning or re-encoding. It calls ``core.attachments`` and keeps a thin
join row (``reimb_attachments``) carrying what only reimbursement knows: which
claim, which checklist item, physical custody, and the GRDS retention class.

**Two doctrines worth stating once.**

*The join table is the source of truth; ``reimb_checklist_items.attachment_ids``
is a display mirror.* ``database-standards.md`` §11 forbids putting anything other
code must join on inside JSONB, and the join row is the one with the FK, the
soft-delete columns and the custody state. Same relationship as
``reimb_claims.status`` to the workflow engine.

*The attachment's holder is the CLAIM, not the checklist item.* Read
authorization is claim-level (``can_read_claim``), and items get soft-deleted and
restored as rules start and stop applying — pinning a file's authorization to a
row that can go dormant would make the file unreachable for reasons that have
nothing to do with who may see it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.attachments import service as core_attachments
from office_connect.core.attachments.authz import (
    AuthzContext,
    register_holder_authorizer,
)
from office_connect.core.attachments.errors import UnauthorizedDownload
from office_connect.core.models import Attachment
from office_connect.core.soft_delete import soft_delete
from office_connect.modules.reimbursement.models import (
    ReimbAttachment,
    ReimbChecklistItem,
)

#: The polymorphic ``core_attachments.holder_kind`` value this module owns.
HOLDER_KIND = "reimb_claim"

#: GRDS 2023: disbursement-voucher supporting records, 10 years from final
#: settlement. Must be a key of ``core.attachments.retention.RETENTION_CLASSES``
#: — an unknown class makes ``retain_until()`` fail safe to None forever, which
#: is how the shipped ``financial_10yr`` default was silently wrong (fixed in
#: migration 0017).
RETENTION_CLASS = "financial_dv_10y"

#: A file whose scan came back infected is quarantined: it exists as a row but
#: must never count as evidence.
_DISQUALIFYING_SCAN = "infected"


async def upload_claim_evidence(
    session: AsyncSession,
    *,
    claim_id: int,
    checklist_item_id: int,
    data: bytes,
    filename: str,
    declared_mime: str | None,
    actor_user_id: int,
) -> tuple[ReimbAttachment, int]:
    """Store a file through core and join it to a claim's checklist item.

    Returns ``(join_row, core_attachment_id)``; the caller enqueues the scan
    after commit (``core.attachments.scan_queue.scan_on_commit``) and owns the
    transaction. Raises ``core.attachments.errors.RejectedUpload`` for a
    disallowed type or an oversized file — the router maps it.

    ``retention_starts_at`` is deliberately left NULL: the GRDS clock runs from
    *final settlement*, which is ``paid_closed`` (or a liquidation's
    ``settled``). Until then ``evaluate_candidate`` reports "retention clock not
    started" and the file is never disposal-eligible, which is the correct
    fail-safe. :func:`start_retention_clock` is what finally starts it (R-7-events).
    """
    result = await core_attachments.upload_attachment(
        session,
        data,
        filename=filename,
        declared_mime=declared_mime,
        holder_kind=HOLDER_KIND,
        holder_id=claim_id,
        retention_class=RETENTION_CLASS,
        retention_starts_at=None,
        actor_id=actor_user_id,
    )

    join = ReimbAttachment(
        claim_id=claim_id,
        attachment_id=result.attachment_id,
        checklist_item_id=checklist_item_id,
        retention_class=RETENTION_CLASS,
    )
    session.add(join)
    await session.flush()
    return join, result.attachment_id


async def remove_claim_evidence(
    session: AsyncSession,
    *,
    join: ReimbAttachment,
    actor_user_id: int,
) -> None:
    """Detach a file: soft-delete the join row AND the core row. Never a hard
    delete of either, and never a touch of the stored bytes (retention)."""
    soft_delete(join, actor_id=actor_user_id)
    await core_attachments.soft_delete_attachment(
        session, join.attachment_id, actor_id=actor_user_id
    )
    await session.flush()


async def store_generated_document(
    session: AsyncSession,
    *,
    claim_id: int,
    checklist_item_id: int,
    data: bytes,
    filename: str,
    actor_user_id: int | None,
) -> tuple[ReimbAttachment, int]:
    """Store a system-rendered PDF through the same core service uploads use.

    Rule 10 in its most literal form: a generated document is bytes plus
    metadata, which is exactly what core-service #2 exists to hold. The only
    difference from an upload is ``origin='generated'``, which tells core the
    bytes are its own output — so they are born ``clean`` and may be previewed
    inline. Validation, hashing, content-addressed storage and retention are
    untouched.
    """
    result = await core_attachments.upload_attachment(
        session,
        data,
        filename=filename,
        declared_mime="application/pdf",
        holder_kind=HOLDER_KIND,
        holder_id=claim_id,
        retention_class=RETENTION_CLASS,
        retention_starts_at=None,
        origin="generated",
        actor_id=actor_user_id,
    )

    join = ReimbAttachment(
        claim_id=claim_id,
        attachment_id=result.attachment_id,
        checklist_item_id=checklist_item_id,
        retention_class=RETENTION_CLASS,
    )
    session.add(join)
    await session.flush()
    return join, result.attachment_id


async def start_retention_clock(
    session: AsyncSession, *, claim_id: int, now: datetime | None = None
) -> int:
    """Start the GRDS clock on a claim's whole file — the promise
    ``upload_claim_evidence`` has been making since R-2 (R-7-events).

    Every upload is stored ``retention_starts_at=None`` because the GRDS-2023
    class is *"disbursement-voucher supporting records, 10 years from final
    settlement"* and nothing on a live claim is finally settled. Nothing had
    ever started it, so ``retain_until()`` returned None for every claim
    attachment in the system and the disposal report reported "retention clock
    not started" forever. This is the one call that ends that, and the two
    callers are the two MONEY terminals: ``paid_closed`` (``record_payout``) and
    ``settled`` (``record_settlement``).

    ``cancelled`` deliberately does NOT call it (user-confirmed at the
    R-7-events kickoff, recorded in the delta register). A voided claim produced
    no disbursement, so dating a disbursement-record retention period from its
    void would assert a disposal deadline for a payment that never happened. Its
    files stay non-disposable — the fail-safe — and stay visible in the disposal
    report as an unanswered question rather than a silently-scheduled one.

    Generated packet PDFs share the holder and are stamped too, which is right:
    the packet IS a DV supporting record, and the copy filed with the voucher is
    the one an auditor asks for.

    Returns the number of attachments stamped. Flushes; the caller commits.
    """
    return await core_attachments.start_retention(
        session, holder_kind=HOLDER_KIND, holder_id=claim_id, at=now
    )


async def evidence_counts(
    session: AsyncSession, *, claim_id: int
) -> dict[int, tuple[int, int, int]]:
    """``checklist_item_id -> (usable, pending, infected)`` in one query.

    A ``pending`` scan counts as usable: the bytes are stored, and blocking a
    claimant because the virus scanner is behind would be a self-inflicted
    outage. Only ``infected`` disqualifies. Both global soft-delete filters
    apply, so a detached file simply stops counting.

    **Uploads only.** A generated document is not evidence the claimant
    supplied, and counting it as such would let a system-produced artifact
    satisfy a ``file_present`` auto-check on a human-evidence item. The
    checklist's ``generated`` status already outranks an upload, so generated
    rows need no representation here at all.
    """
    rows = (
        await session.execute(
            select(ReimbAttachment.checklist_item_id, Attachment.scan_status)
            .join(Attachment, Attachment.id == ReimbAttachment.attachment_id)
            .where(
                ReimbAttachment.claim_id == claim_id,
                ReimbAttachment.checklist_item_id.is_not(None),
                Attachment.origin == "uploaded",
            )
        )
    ).all()

    counts: dict[int, tuple[int, int, int]] = {}
    for item_id, scan_status in rows:
        usable, pending, infected = counts.get(item_id, (0, 0, 0))
        if scan_status == _DISQUALIFYING_SCAN:
            infected += 1
        else:
            usable += 1
            if scan_status == "pending":
                pending += 1
        counts[item_id] = (usable, pending, infected)
    return counts


async def claim_evidence(
    session: AsyncSession, *, claim_id: int
) -> dict[int, list[dict[str, Any]]]:
    """``checklist_item_id -> [render-ready file dicts]`` for the packet screen."""
    rows = (
        await session.execute(
            select(ReimbAttachment, Attachment)
            .join(Attachment, Attachment.id == ReimbAttachment.attachment_id)
            .where(
                ReimbAttachment.claim_id == claim_id,
                ReimbAttachment.checklist_item_id.is_not(None),
            )
            .order_by(ReimbAttachment.id)
        )
    ).all()

    by_item: dict[int, list[dict[str, Any]]] = {}
    for join, attachment in rows:
        by_item.setdefault(join.checklist_item_id, []).append(
            {
                "id": join.id,
                "attachment_id": attachment.id,
                "filename": attachment.original_filename,
                "byte_size": attachment.byte_size,
                "scan_status": attachment.scan_status,
                "uploaded_at": join.created_at,
                "origin": attachment.origin,
                # Only a clean file is servable — `download_attachment` refuses
                # anything else, so offering a link would be a lie. Generated
                # PDFs are born clean, so their link is available immediately.
                "download_path": (
                    f"/api/v1/attachments/{attachment.id}/content"
                    if attachment.scan_status == "clean"
                    else None
                ),
            }
        )
    return by_item


def mirror_attachment_ids(item: ReimbChecklistItem, ids: list[int]) -> None:
    """Rewrite the display mirror.

    REASSIGNS the list — the column has no ``MutableList``, so an in-place
    ``.append()`` would leave the row un-dirty and the change would silently not
    persist. (Same reason ``drafts.py`` reassigns ``claim.totals``.)
    """
    item.attachment_ids = list(ids)


# --------------------------------------------------------------------------
# Download authorization (the seam core/attachments/authz.py was built for)
# --------------------------------------------------------------------------


async def authorize_claim_attachment(row: Attachment, ctx: AuthzContext) -> None:
    """Gate a download of a claim's file by the claim's OWN read rule.

    The core route's ``require_permission("attachment.download")`` is coarse —
    the ``staff`` role holds it globally. This is the real scoping: the owner, or
    an actor whose approve/review/fms_update grant covers the claim's org unit.
    Raising anything denies (core converts it to ``UnauthorizedDownload``), so
    the fail-closed direction is automatic.
    """
    # Imported here, not at module scope: `api.deps` imports the checklist
    # service, which imports this module — a top-level import would close the
    # cycle. The seam is a runtime callback, so a deferred import is honest.
    from office_connect.modules.reimbursement.api.deps import can_read_claim, get_claim

    if row.holder_id is None:
        raise UnauthorizedDownload("claim attachment with no claim")
    claim = await get_claim(ctx.session, row.holder_id)
    if not await can_read_claim(
        ctx.session, actor_user_id=ctx.principal.user_id, claim=claim
    ):
        raise UnauthorizedDownload("not permitted to read this claim")


# Module-level registration, mirroring `ops/attachments_tasks.py`'s enqueuer
# injection. It reaches the app because main.py imports the reimbursement
# router, which imports api/checklist.py, which imports this service — so
# wiring reimbursement into core's download route needs ZERO core change,
# exactly as core/attachments/authz.py's docstring promised at Stage B.
register_holder_authorizer(HOLDER_KIND, authorize_claim_attachment)
