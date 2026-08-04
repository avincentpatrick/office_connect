"""Frozen-snapshot signatures — core-service #3 (master-plan §1.1).

Five operations, all polymorphic over ``(subject_kind, subject_id)`` so the
service never learns what a claim is:

``freeze_snapshot``   record a rendered PDF as the official copy of one document
``void_snapshots``    invalidate copies because their inputs changed
``active_snapshots``  the live official copies for a subject
``find_active``       one live copy, by document key
``stale_snapshots``   the "modified after signature" re-flag

Scope note (R-5): this is the **snapshot half** of #3. Signature *capture* —
certification steps A/B/C and external wet-sign — is deferred to R-6, where the
liquidation chain and its signatories actually exist and the signatory config
question with the resident COA auditor is settled. What ships now is everything a
signature will later bind to.

**Why superseded and voided are different states.** Both retire a snapshot and
both keep the row. But ``superseded`` is the ordinary course — a draft replaced
by the filed original, or a resubmission reissuing its packet — while ``voided``
records that a document was invalidated because the data underneath it moved.
An auditor asking "was this ever changed after it was approved?" is asking for
voided rows specifically; collapsing the two into a boolean would erase exactly
the fact the service exists to preserve.

Every write flushes and never commits — the module-wide transaction contract.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.models.document_snapshot import DocumentSnapshot
from office_connect.core.time import utc_now

ACTIVE = "active"
SUPERSEDED = "superseded"
VOIDED = "voided"


async def find_active(
    session: AsyncSession,
    *,
    subject_kind: str,
    subject_id: int,
    document_key: str,
) -> DocumentSnapshot | None:
    """The live official copy of one document, if any."""
    return (
        await session.execute(
            select(DocumentSnapshot).where(
                DocumentSnapshot.subject_kind == subject_kind,
                DocumentSnapshot.subject_id == subject_id,
                DocumentSnapshot.document_key == document_key,
                DocumentSnapshot.status == ACTIVE,
            )
        )
    ).scalar_one_or_none()


async def active_snapshots(
    session: AsyncSession, *, subject_kind: str, subject_id: int
) -> list[DocumentSnapshot]:
    """Every live official copy for a subject, oldest first."""
    return list(
        (
            await session.execute(
                select(DocumentSnapshot)
                .where(
                    DocumentSnapshot.subject_kind == subject_kind,
                    DocumentSnapshot.subject_id == subject_id,
                    DocumentSnapshot.status == ACTIVE,
                )
                .order_by(DocumentSnapshot.document_key)
            )
        )
        .scalars()
        .all()
    )


async def freeze_snapshot(
    session: AsyncSession,
    *,
    subject_kind: str,
    subject_id: int,
    document_key: str,
    attachment_id: int,
    content_sha256: str,
    source_fingerprint: str,
    revision_no: int | None = None,
    is_draft: bool = False,
    actor_id: int | None = None,
    now: datetime | None = None,
) -> DocumentSnapshot:
    """Record a rendered PDF as the official copy, superseding any predecessor.

    Supersession is unconditional: the caller decides whether to render at all
    (and short-circuits when nothing changed), so reaching this function always
    means a new official copy exists. Marking the predecessor ``superseded``
    rather than voided is correct here — this is the ordinary reissue path.
    """
    stamp = now or utc_now()

    previous = await find_active(
        session,
        subject_kind=subject_kind,
        subject_id=subject_id,
        document_key=document_key,
    )
    if previous is not None:
        previous.status = SUPERSEDED

    row = DocumentSnapshot(
        subject_kind=subject_kind,
        subject_id=subject_id,
        document_key=document_key,
        attachment_id=attachment_id,
        content_sha256=content_sha256,
        source_fingerprint=source_fingerprint,
        revision_no=revision_no,
        is_draft=is_draft,
        status=ACTIVE,
        generated_by=actor_id,
        generated_at=stamp,
        created_by=actor_id,
    )
    session.add(row)
    await session.flush()
    return row


async def void_snapshots(
    session: AsyncSession,
    *,
    subject_kind: str,
    subject_id: int,
    reason: str,
    document_key: str | None = None,
    actor_id: int | None = None,
    now: datetime | None = None,
) -> list[DocumentSnapshot]:
    """Invalidate live copies whose inputs changed. Returns what was voided.

    This is spec §10's *"regeneration after any edit voids prior snapshots"*.
    Note it voids the filed original as readily as a draft — that is the point.
    A claim returned for correction and then edited has a signed packet that no
    longer describes it, and leaving that snapshot active would let a stale
    approval carry forward. Voiding it is what forces the fresh approval spec §7
    rule 6 requires.
    """
    stamp = now or utc_now()

    query = select(DocumentSnapshot).where(
        DocumentSnapshot.subject_kind == subject_kind,
        DocumentSnapshot.subject_id == subject_id,
        DocumentSnapshot.status == ACTIVE,
    )
    if document_key is not None:
        query = query.where(DocumentSnapshot.document_key == document_key)

    rows = list((await session.execute(query)).scalars().all())
    for row in rows:
        row.status = VOIDED
        row.voided_at = stamp
        row.voided_by = actor_id
        row.void_reason = reason
    if rows:
        await session.flush()
    return rows


async def stale_snapshots(
    session: AsyncSession,
    *,
    subject_kind: str,
    subject_id: int,
    fingerprints: dict[str, str],
) -> list[DocumentSnapshot]:
    """The "modified after signature" re-flag.

    Given the fingerprints the subject's data would produce **right now**,
    return the live snapshots that no longer match — i.e. documents someone may
    already have signed whose underlying facts have since moved.

    Read-only by design. It reports; it does not void. Whether a divergence
    should invalidate a signature, merely warn an approver, or force a
    resubmission is a workflow decision, and core-service #3 must not make it on
    every consumer's behalf.

    A key absent from ``fingerprints`` is skipped rather than treated as stale:
    the caller may legitimately be asking about a subset of documents.
    """
    rows = await active_snapshots(
        session, subject_kind=subject_kind, subject_id=subject_id
    )
    return [
        row
        for row in rows
        if row.document_key in fingerprints
        and fingerprints[row.document_key] != row.source_fingerprint
    ]
