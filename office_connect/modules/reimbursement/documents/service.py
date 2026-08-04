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
    build_document_context,
    is_draft_claim,
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


async def _bindings(
    session: AsyncSession, *, claim_kind: str
) -> list[ReimbTemplateMap]:
    """Active template bindings for a claim kind, in print order."""
    rows = (
        await session.execute(
            select(ReimbTemplateMap)
            .where(
                ReimbTemplateMap.is_active.is_(True),
                ReimbTemplateMap.claim_kind.in_([claim_kind, None]),
            )
            .order_by(ReimbTemplateMap.sort, ReimbTemplateMap.id)
        )
    ).scalars()
    return list(rows)


def _filename(claim: ReimbClaim, binding: ReimbTemplateMap, stamp: datetime) -> str:
    """Spec §5.7's convention: ``[RefNo]_[YYYYMMDD]_[HHMMSS]``.

    A draft has no reference number, so it is stamped ``DRAFT-<claim id>``
    instead. The two can never be confused in a folder listing, which is the
    point of the convention in the first place.
    """
    local = to_manila(stamp)
    stem = claim.ref_no or f"DRAFT-{claim.id}"
    return (
        f"{stem}_{local:%Y%m%d}_{local:%H%M%S}_{binding.checklist_code}.pdf"
    )


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

    for binding in await _bindings(session, claim_kind=claim.kind):
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

    # The idempotence check. `generated_at` is excluded from the comparison —
    # it changes on every pass by construction, so including it would make every
    # regeneration "different" and defeat the whole mechanism.
    comparable = {**context, "doc": {**context["doc"], "generated_at": None}}
    fingerprint = fingerprint_context(comparable)

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
        filename=_filename(claim, binding, stamp),
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
    )
