"""Generate a claim's documentary packet (R-5, Objective 1).

The orchestration that turns claim data into filed PDFs:

    for each bound document
        build context  →  fingerprint  →  render  →  store as a core attachment
                       →  freeze a snapshot  →  flip the checklist item

Three properties this function must have, and how each is obtained:

**Idempotent** (spec §10: "Celery task, idempotent, 3 retries"). Before
rendering, the live snapshot's ``source_fingerprint`` is compared with the one
the current data produces. Equal, and with the same draft-ness, means the stored
PDF is already correct: no render, no attachment, no audit row. This is what
makes a retried task free and a double-click harmless.

**Non-blocking on failure** (§19.12). A single document that fails to render does
not abort the others, and nothing here raises into a request path — the caller is
a Celery task. The claim keeps its data; the item simply stays un-generated and
visibly not done, which is honest and retryable.

**Never fabricates money.** ``build_document_context`` refuses a claim with no
``totals`` snapshot rather than printing zeros.

Regeneration semantics come free from ``freeze_snapshot``: the previous active
snapshot is marked ``superseded`` and the new one becomes the official copy, so
the draft a claimant previewed is automatically retired by the authoritative
version generated at submit.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.documents import (
    RenderFailed,
    fingerprint_context,
    freeze_snapshot,
    render_document,
)
from office_connect.core.documents.render import PdfRenderer
from office_connect.core.documents.snapshots import find_active
from office_connect.core.time import to_manila, utc_now
from office_connect.modules.reimbursement.documents import registry  # noqa: F401
from office_connect.modules.reimbursement.documents.context import (
    PacketSection,
    build_document_context,
    build_packet_context,
    is_draft_claim,
)
from office_connect.modules.reimbursement.documents.registry import (
    PACKET,
    PACKET_TITLE,
    PACKET_TITLES,
)
from office_connect.modules.reimbursement.models import (
    ReimbClaim,
    ReimbTemplateMap,
)
from office_connect.modules.reimbursement.services import attachments as evidence
from office_connect.modules.reimbursement.services import checklist

logger = logging.getLogger(__name__)

#: ``core_document_snapshots.subject_kind`` this module owns. Aliased to the
#: attachment holder kind rather than re-spelled: they are different columns in
#: different core tables, but both name the same entity, and two string literals
#: that must agree forever are one typo away from a silent mismatch.
SUBJECT_KIND = evidence.HOLDER_KIND


@dataclass(frozen=True)
class GeneratedDocument:
    """What happened to one document in a generation pass."""

    document_key: str
    checklist_code: str
    outcome: str  # 'generated' | 'unchanged' | 'failed'
    attachment_id: int | None = None
    detail: str | None = None
    #: The live copy's content hash — from this pass when it rendered, from the
    #: existing snapshot when it did not. The packet's cover prints these, which
    #: is why an 'unchanged' result must still carry one.
    content_sha256: str | None = None


async def _bindings(
    session: AsyncSession, *, claim_kind: str
) -> list[ReimbTemplateMap]:
    """Active template bindings for a claim kind, in print order.

    ``claim_kind IS NULL`` means "both kinds" (``models/templates.py``), and
    matching it needs the explicit ``IS NULL`` arm: SQL ``IN (x, NULL)`` never
    matches a NULL, so the previous ``.in_([claim_kind, None])`` made that
    documented semantic unreachable. Fixed at R-6-liq-settle while the blast
    radius was still provably zero (every seeded row names its kind), which is
    when a predicate should be fixed — the failure mode is silent, and what goes
    missing is a government form. Same shape as
    ``services/checklist.py::_catalog``, which had it right all along.
    """
    rows = (
        await session.execute(
            select(ReimbTemplateMap)
            .where(
                ReimbTemplateMap.is_active.is_(True),
                (ReimbTemplateMap.claim_kind.is_(None))
                | (ReimbTemplateMap.claim_kind == claim_kind),
            )
            .order_by(ReimbTemplateMap.sort, ReimbTemplateMap.id)
        )
    ).scalars()
    return list(rows)


def _filename(claim: ReimbClaim, suffix: str, stamp: datetime) -> str:
    """Spec §5.7's convention: ``[RefNo]_[YYYYMMDD]_[HHMMSS]``.

    A draft has no reference number, so it is stamped ``DRAFT-<claim id>``
    instead. The two can never be confused in a folder listing, which is the
    point of the convention in the first place.
    """
    local = to_manila(stamp)
    stem = claim.ref_no or f"DRAFT-{claim.id}"
    return f"{stem}_{local:%Y%m%d}_{local:%H%M%S}_{suffix}.pdf"


def comparable_context(context: dict) -> dict:
    """The context as it is HASHED, rather than as it is rendered.

    Two fields are excluded, for the same underlying reason — both are outputs
    of the pass, not inputs to it, so including either would make every
    regeneration look different and defeat fingerprint idempotence entirely:

    ``doc.generated_at``  changes on every pass by construction.
    ``doc.fingerprint``   IS the value being computed (the packet prints it, so
                          it must be in the render context but cannot be in the
                          hashed one — a hash cannot contain itself).

    Every document path must hash through this one function. Two call sites
    computing "comparable" slightly differently would make one of them look
    permanently stale.
    """
    return {**context, "doc": {**context["doc"], "generated_at": None, "fingerprint": None}}


async def generate_claim_documents(
    session: AsyncSession,
    *,
    claim_id: int,
    actor_user_id: int | None = None,
    now: datetime | None = None,
    renderer: PdfRenderer | None = None,
) -> list[GeneratedDocument]:
    """Render, store and file every bound document for one claim.

    Flushes, never commits — the caller owns the transaction.
    """
    stamp = now or utc_now()

    claim = (
        await session.execute(select(ReimbClaim).where(ReimbClaim.id == claim_id))
    ).scalar_one_or_none()
    if claim is None:
        raise checklist.errors.claim_not_found()

    draft = is_draft_claim(claim)
    revision_no = None
    results: list[GeneratedDocument] = []

    bindings = await _bindings(session, claim_kind=claim.kind)
    for binding in bindings:
        result = await _generate_one(
            session,
            claim=claim,
            binding=binding,
            draft=draft,
            revision_no=revision_no,
            actor_user_id=actor_user_id,
            stamp=stamp,
            renderer=renderer,
        )
        results.append(result)

    # The packet goes LAST, deliberately: its cover prints the content hash of
    # every form it contains, so those forms must already exist this pass.
    by_key = {result.document_key: result for result in results}
    sections = [
        PacketSection(
            document_key=binding.document_key,
            checklist_code=binding.checklist_code,
            title=binding.title,
            form_no=binding.form_no,
            content_sha256=(
                by_key[binding.document_key].content_sha256
                if binding.document_key in by_key
                else None
            ),
        )
        for binding in bindings
    ]
    results.append(
        await _generate_packet(
            session,
            claim=claim,
            sections=sections,
            draft=draft,
            revision_no=revision_no,
            actor_user_id=actor_user_id,
            stamp=stamp,
            renderer=renderer,
        )
    )

    return results


async def _generate_one(
    session: AsyncSession,
    *,
    claim: ReimbClaim,
    binding: ReimbTemplateMap,
    draft: bool,
    revision_no: int | None,
    actor_user_id: int | None,
    stamp: datetime,
    renderer: PdfRenderer | None,
) -> GeneratedDocument:
    try:
        context = await build_document_context(
            session,
            claim=claim,
            document_key=binding.document_key,
            title=binding.title,
            form_no=binding.form_no,
            now=stamp,
        )
    except Exception as exc:  # missing totals, vanished staff row, …
        logger.warning(
            "document context failed",
            extra={
                "claim_id": claim.id,
                "document_key": binding.document_key,
                "error": str(exc),
            },
        )
        return GeneratedDocument(
            document_key=binding.document_key,
            checklist_code=binding.checklist_code,
            outcome="failed",
            detail=str(exc),
        )

    # The idempotence check — see `comparable_context` for what is excluded and
    # why. Equal fingerprint and equal draft-ness means the stored PDF is
    # already correct: no render, no attachment, no audit row.
    fingerprint = fingerprint_context(comparable_context(context))

    existing = await find_active(
        session,
        subject_kind=SUBJECT_KIND,
        subject_id=claim.id,
        document_key=binding.document_key,
    )
    if (
        existing is not None
        and existing.source_fingerprint == fingerprint
        and existing.is_draft == draft
    ):
        return GeneratedDocument(
            document_key=binding.document_key,
            checklist_code=binding.checklist_code,
            outcome="unchanged",
            attachment_id=existing.attachment_id,
            content_sha256=existing.content_sha256,
        )

    try:
        rendered = render_document(
            key=binding.document_key,
            context=context,
            branding=context.get("branding"),
            renderer=renderer,
        )
    except RenderFailed as exc:
        logger.warning(
            "document render failed",
            extra={
                "claim_id": claim.id,
                "document_key": binding.document_key,
                "error": str(exc),
            },
        )
        return GeneratedDocument(
            document_key=binding.document_key,
            checklist_code=binding.checklist_code,
            outcome="failed",
            detail=str(exc),
        )

    item = await checklist.materialize_generated_item(
        session,
        claim=claim,
        code=binding.checklist_code,
        actor_user_id=actor_user_id,
    )

    _join, attachment_id = await evidence.store_generated_document(
        session,
        claim_id=claim.id,
        checklist_item_id=item.id,
        data=rendered.pdf,
        filename=_filename(claim, binding.checklist_code, stamp),
        actor_user_id=actor_user_id,
    )

    await freeze_snapshot(
        session,
        subject_kind=SUBJECT_KIND,
        subject_id=claim.id,
        document_key=binding.document_key,
        attachment_id=attachment_id,
        content_sha256=rendered.content_sha256,
        # Store the COMPARABLE fingerprint, not one over the raw context — the
        # next pass recomputes it the same way, and a mismatch of method would
        # make every document look permanently stale.
        source_fingerprint=fingerprint,
        revision_no=revision_no,
        is_draft=draft,
        actor_id=actor_user_id,
        now=stamp,
    )

    await checklist.mark_generated(
        session,
        claim=claim,
        item=item,
        attachment_id=attachment_id,
        actor_user_id=actor_user_id,
    )

    return GeneratedDocument(
        document_key=binding.document_key,
        checklist_code=binding.checklist_code,
        outcome="generated",
        attachment_id=attachment_id,
        content_sha256=rendered.content_sha256,
    )


async def _generate_packet(
    session: AsyncSession,
    *,
    claim: ReimbClaim,
    sections: list[PacketSection],
    draft: bool,
    revision_no: int | None,
    actor_user_id: int | None,
    stamp: datetime,
    renderer: PdfRenderer | None,
) -> GeneratedDocument:
    """Render the combined packet — the same pipeline, minus the checklist.

    Three deliberate differences from ``_generate_one``, all following from the
    packet being a **claim-level artifact** rather than a checklist document:

    - no ``materialize_generated_item`` and no ``mark_generated``. No COA
      circular names a "packet"; the circulars name the documents inside it. A
      catalog row invented for the folder would put a system artifact into the
      FS-BD-01 checklist and give a claimant a requirement they cannot satisfy.
    - ``checklist_item_id=None`` on the join row. ``claim_evidence`` and
      ``evidence_counts`` both already filter ``checklist_item_id IS NOT NULL``,
      so the packet is invisible to the Documents task list and uncountable as
      evidence with **no filter change anywhere**.
    - the fingerprint is injected back into the context before rendering, so the
      cover can print it (see ``comparable_context``).

    Failure is non-blocking and symmetrical (§19.12): a packet that cannot
    render leaves the three forms exactly as they are, and vice versa.
    """
    # Per-kind heading (R-6-liq-settle). Resolved from the code-side map rather
    # than a second DocumentSpec: forking the KEY would fork the snapshot
    # lineage for one string, since `find_active` resolves on `document_key`.
    packet_title = PACKET_TITLES.get(claim.kind or "", PACKET_TITLE)
    try:
        context = await build_packet_context(
            session,
            claim=claim,
            sections=sections,
            title=packet_title,
            now=stamp,
        )
    except Exception as exc:  # missing totals, vanished staff row, …
        logger.warning(
            "packet context failed",
            extra={"claim_id": claim.id, "document_key": PACKET, "error": str(exc)},
        )
        return GeneratedDocument(
            document_key=PACKET,
            checklist_code=PACKET_TITLE,
            outcome="failed",
            detail=str(exc),
        )

    fingerprint = fingerprint_context(comparable_context(context))
    # Render-only: `comparable_context` nulls it again on the next pass, so the
    # packet can print its own fingerprint without the value chasing itself.
    context["doc"]["fingerprint"] = fingerprint

    existing = await find_active(
        session,
        subject_kind=SUBJECT_KIND,
        subject_id=claim.id,
        document_key=PACKET,
    )
    if (
        existing is not None
        and existing.source_fingerprint == fingerprint
        and existing.is_draft == draft
    ):
        return GeneratedDocument(
            document_key=PACKET,
            checklist_code=PACKET_TITLE,
            outcome="unchanged",
            attachment_id=existing.attachment_id,
            content_sha256=existing.content_sha256,
        )

    try:
        rendered = render_document(
            key=PACKET,
            context=context,
            branding=context.get("branding"),
            renderer=renderer,
        )
    except RenderFailed as exc:
        logger.warning(
            "packet render failed",
            extra={"claim_id": claim.id, "document_key": PACKET, "error": str(exc)},
        )
        return GeneratedDocument(
            document_key=PACKET,
            checklist_code=PACKET_TITLE,
            outcome="failed",
            detail=str(exc),
        )

    _join, attachment_id = await evidence.store_generated_document(
        session,
        claim_id=claim.id,
        checklist_item_id=None,
        data=rendered.pdf,
        filename=_filename(claim, "PACKET", stamp),
        actor_user_id=actor_user_id,
    )

    await freeze_snapshot(
        session,
        subject_kind=SUBJECT_KIND,
        subject_id=claim.id,
        document_key=PACKET,
        attachment_id=attachment_id,
        content_sha256=rendered.content_sha256,
        source_fingerprint=fingerprint,
        revision_no=revision_no,
        is_draft=draft,
        actor_id=actor_user_id,
        now=stamp,
    )

    return GeneratedDocument(
        document_key=PACKET,
        checklist_code=PACKET_TITLE,
        outcome="generated",
        attachment_id=attachment_id,
        content_sha256=rendered.content_sha256,
    )
