"""Authenticated attachments HTTP router (Stage B / Increment 4).

Gives the Increment-4 attachment service real ``/api/v1`` routes, each gated by a
permission STRING (``attachment.*``). Upload owns the unit of work — validate +
store + persist a ``pending`` row, then enqueue the scan (``ops.scan_attachment``)
after commit; download is fail-closed, streams the sanitized derivative, and runs
the per-row authorize hook (the Stage-C holder-scoping seam). Service exceptions
map to the structured error envelope.
"""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.api.errors import APIError
from office_connect.core.api.schemas.attachments import (
    AttachmentSummary,
    DisposalCandidateResponse,
    DisposalReportResponse,
)
from office_connect.core.api.schemas.auth import OkResponse
from office_connect.core.attachments import service
from office_connect.core.attachments.authz import AuthzContext, make_download_authorizer
from office_connect.core.attachments.errors import (
    AttachmentError,
    AttachmentNotFound,
    DownloadNotReady,
    RejectedUpload,
    UnauthorizedDownload,
)
from office_connect.core.attachments.scan_queue import scan_on_commit
from office_connect.core.auth.dependencies import require_permission
from office_connect.core.auth.principal import Principal
from office_connect.core.config import get_settings
from office_connect.core.db import get_session
from office_connect.core.models import Attachment

router = APIRouter()

# Service exception → (HTTP status, error.code, client message).
_ERROR_MAP: dict[type[AttachmentError], tuple[int, str, str]] = {
    RejectedUpload: (422, "attachment_rejected", "The file type is not allowed."),
    AttachmentNotFound: (404, "not_found", "Attachment not found."),
    UnauthorizedDownload: (403, "forbidden", "You do not have permission to do that."),
    DownloadNotReady: (
        409,
        "attachment_not_ready",
        "The attachment is not available for download yet.",
    ),
}


def _as_api_error(exc: AttachmentError) -> APIError:
    for exc_type, (status, code, message) in _ERROR_MAP.items():
        if isinstance(exc, exc_type):
            return APIError(status, code, message)
    return APIError(500, "internal_error", "An internal error occurred.")


def _summary(row: Attachment, *, deduped: bool | None = None) -> AttachmentSummary:
    return AttachmentSummary(
        id=row.id,
        original_filename=row.original_filename,
        sniffed_mime=row.sniffed_mime,
        media_kind=row.media_kind,
        byte_size=row.byte_size,
        sha256=row.sha256,
        scan_status=row.scan_status,
        scanned_at=row.scanned_at,
        holder_kind=row.holder_kind,
        holder_id=row.holder_id,
        retention_class=row.retention_class,
        legal_hold=row.legal_hold,
        disposed_at=row.disposed_at,
        created_at=row.created_at,
        created_by=row.created_by,
        deduped=deduped,
    )


async def _read_capped(file: UploadFile, max_bytes: int) -> bytes:
    """Read the upload into memory, aborting at the size cap (deterministic 413)."""
    if file.size is not None and file.size > max_bytes:  # cheap early reject
        raise APIError(413, "payload_too_large", "The file exceeds the maximum size.")
    buf = bytearray()
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        buf.extend(chunk)
        if len(buf) > max_bytes:
            raise APIError(
                413, "payload_too_large", "The file exceeds the maximum size."
            )
    return bytes(buf)


@router.post("/attachments", response_model=AttachmentSummary, status_code=201)
async def upload_attachment(
    request: Request,
    file: UploadFile = File(...),
    holder_kind: str | None = Form(None),
    holder_id: int | None = Form(None),
    principal: Principal = Depends(require_permission("attachment.upload")),
    session: AsyncSession = Depends(get_session),
):
    settings = get_settings()
    data = await _read_capped(file, settings.attachment_max_bytes)
    try:
        result = await service.upload_attachment(
            session,
            data,
            filename=file.filename or "upload",
            declared_mime=file.content_type,
            holder_kind=holder_kind,
            holder_id=holder_id,
            actor_id=principal.user_id,
            settings=settings,
        )
    except AttachmentError as exc:
        raise _as_api_error(exc) from exc
    # Enqueue the scan strictly after commit (the row must be visible first); if no
    # worker is wired, the beat sweeper drains the pending row.
    scan_on_commit(session, result.attachment_id)
    await session.commit()

    row = (
        await session.execute(
            select(Attachment).where(Attachment.id == result.attachment_id)
        )
    ).scalar_one()
    return _summary(row, deduped=result.deduped)


@router.get("/attachments/disposal-report", response_model=DisposalReportResponse)
async def disposal_report(
    _: Principal = Depends(require_permission("attachment.dispose.read")),
    session: AsyncSession = Depends(get_session),
):
    candidates = await service.disposal_eligibility_report(session)
    return DisposalReportResponse(
        candidates=[
            DisposalCandidateResponse(
                attachment_id=c.attachment_id,
                sha256=c.sha256,
                retention_class=c.retention_class,
                retention_starts_at=c.retention_starts_at,
                retain_until=c.retain_until,
                legal_hold=c.legal_hold,
                eligible=c.eligible,
                reason=c.reason,
            )
            for c in candidates
        ]
    )


@router.get("/attachments/{attachment_id}", response_model=AttachmentSummary)
async def get_attachment(
    attachment_id: int,
    _: Principal = Depends(require_permission("attachment.read")),
    session: AsyncSession = Depends(get_session),
):
    row = (
        await session.execute(
            select(Attachment).where(Attachment.id == attachment_id)
        )
    ).scalar_one_or_none()
    if row is None:  # soft-deleted rows are filtered out → treated as absent
        raise APIError(404, "not_found", "Attachment not found.")
    return _summary(row)


@router.get("/attachments/{attachment_id}/content")
async def download_attachment(
    attachment_id: int,
    principal: Principal = Depends(require_permission("attachment.download")),
    session: AsyncSession = Depends(get_session),
):
    authorize = make_download_authorizer(
        AuthzContext(principal=principal, session=session)
    )
    try:
        dl = await service.download_attachment(
            session, attachment_id, authorize=authorize
        )
    except AttachmentError as exc:
        raise _as_api_error(exc) from exc

    def _iter():
        try:
            while True:
                chunk = dl.stream.read(64 * 1024)
                if not chunk:
                    break
                yield chunk
        finally:
            dl.stream.close()

    ascii_name = dl.filename.encode("ascii", "ignore").decode() or "download"
    disposition = (
        f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(dl.filename)}'
    )
    return StreamingResponse(
        _iter(),
        media_type=dl.content_type,
        headers={
            "Content-Length": str(dl.size),
            "Content-Disposition": disposition,
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete("/attachments/{attachment_id}", response_model=OkResponse)
async def delete_attachment(
    attachment_id: int,
    principal: Principal = Depends(require_permission("attachment.delete")),
    session: AsyncSession = Depends(get_session),
):
    try:
        await service.soft_delete_attachment(
            session, attachment_id, actor_id=principal.user_id
        )
    except AttachmentError as exc:
        raise _as_api_error(exc) from exc
    await session.commit()
    return OkResponse()
