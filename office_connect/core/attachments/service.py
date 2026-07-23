"""Attachment service orchestration — the API modules consume (Rule 10).

Upload (validate → hash → store → persist ``pending``) is synchronous and
fail-fast; scan + re-encode run later via ``process_attachment`` (driven by the
``ops`` Celery task, since ``core`` may not import the worker). Download is
fail-closed and gated by an injected ``authorize`` hook — the Stage-B HTTP router
supplies the real RBAC closure; today tests inject allow/deny.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from datetime import datetime
from typing import Awaitable, BinaryIO, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.attachments import pipeline, retention
from office_connect.core.attachments.errors import (
    AttachmentNotFound,
    DownloadNotReady,
    RejectedUpload,
    UnauthorizedDownload,
)
from office_connect.core.attachments.scanner import Scanner, get_scanner
from office_connect.core.config import Settings, get_settings
from office_connect.core.models import Attachment
from office_connect.core.soft_delete import soft_delete
from office_connect.core.storage import (
    StorageDriver,
    StorageError,
    get_storage_driver,
    sha256_hex,
)
from office_connect.core.time import utc_now

# authorize(row) may be sync or async; it raises/returns to allow, or raises to deny.
AuthorizeHook = Callable[[Attachment], "Awaitable[None] | None"]


@dataclass(frozen=True)
class UploadResult:
    attachment_id: int
    sha256: str
    scan_status: str
    deduped: bool


@dataclass(frozen=True)
class AttachmentDownload:
    filename: str
    content_type: str
    size: int
    sha256: str
    stream: BinaryIO


async def upload_attachment(
    session: AsyncSession,
    data: bytes,
    *,
    filename: str,
    declared_mime: str | None = None,
    holder_kind: str | None = None,
    holder_id: int | None = None,
    retention_class: str = "default",
    retention_starts_at: datetime | None = None,
    actor_id: int | None = None,
    settings: Settings | None = None,
    storage: StorageDriver | None = None,
) -> UploadResult:
    """Validate, store, and persist a ``pending`` attachment. Does not scan."""
    settings = settings or get_settings()
    storage = storage or get_storage_driver(settings)

    validated = pipeline.validate_upload(
        data, max_bytes=settings.attachment_max_bytes, declared_mime=declared_mime
    )
    key = sha256_hex(data)
    deduped = storage.exists(key)
    stored = storage.save(data, content_type=validated.sniffed_mime, filename=filename)

    row = Attachment(
        holder_kind=holder_kind,
        holder_id=holder_id,
        original_filename=filename,
        sniffed_mime=validated.sniffed_mime,
        declared_mime=declared_mime,
        byte_size=stored.size,
        sha256=stored.key,
        storage_backend=storage.name,
        media_kind=validated.media_kind,
        scan_status="pending",
        retention_class=retention_class,
        retention_starts_at=retention_starts_at,
        created_by=actor_id,
    )
    session.add(row)
    await session.flush()
    return UploadResult(
        attachment_id=row.id,
        sha256=stored.key,
        scan_status="pending",
        deduped=deduped,
    )


async def process_attachment(
    session: AsyncSession,
    attachment_id: int,
    *,
    scanner: Scanner | None = None,
    storage: StorageDriver | None = None,
    settings: Settings | None = None,
) -> str:
    """Scan a ``pending`` attachment and, if clean, re-encode images. Returns the
    resulting ``scan_status``. Idempotent: a non-pending row is returned as-is."""
    settings = settings or get_settings()
    storage = storage or get_storage_driver(settings)
    scanner = scanner or get_scanner(settings)

    row = (
        await session.execute(select(Attachment).where(Attachment.id == attachment_id))
    ).scalar_one_or_none()
    if row is None:
        raise AttachmentNotFound(f"attachment {attachment_id} not found")
    # 'error' rows are retryable (transient scanner/storage outage); terminal
    # 'clean'/'infected' are returned as-is (idempotent).
    if row.scan_status not in ("pending", "error"):
        return row.scan_status

    def _mark_error(signature: str, scanner_name: str) -> None:
        row.scan_status = "error"
        row.scan_signature = signature
        row.scanned_at = utc_now()
        row.scanner_name = scanner_name

    try:
        original = storage.read(row.sha256)
    except StorageError as exc:  # missing/unreadable blob → fail-closed error
        _mark_error(f"blob-unreadable: {exc}", "storage")
        await session.flush()
        return "error"

    result = scanner.scan(original)
    row.scan_status = result.status
    row.scan_signature = result.signature
    row.scanned_at = utc_now()
    row.scanner_name = result.scanner_name

    if result.status == "clean" and row.media_kind == "image":
        try:
            clean_bytes, served_mime = pipeline.reencode_image(
                original, row.sniffed_mime
            )
        except RejectedUpload as exc:  # passed scan but won't re-encode → error
            _mark_error(f"reencode-failed: {exc}", result.scanner_name)
            await session.flush()
            return "error"
        sanitized = storage.save(clean_bytes, content_type=served_mime)
        row.sanitized_sha256 = sanitized.key
        row.sanitized_mime = served_mime
        row.sanitized_byte_size = sanitized.size
        row.sanitized_at = utc_now()

    await session.flush()
    return row.scan_status


async def download_attachment(
    session: AsyncSession,
    attachment_id: int,
    *,
    authorize: AuthorizeHook,
    storage: StorageDriver | None = None,
    settings: Settings | None = None,
) -> AttachmentDownload:
    """Fail-closed, auth-checked streaming read. Serves the sanitized derivative
    for images. Gate order: soft-delete → authorize → clean → not-disposed."""
    settings = settings or get_settings()
    storage = storage or get_storage_driver(settings)

    row = (
        await session.execute(select(Attachment).where(Attachment.id == attachment_id))
    ).scalar_one_or_none()
    if row is None:  # soft-deleted rows are filtered out → treated as absent
        raise AttachmentNotFound(f"attachment {attachment_id} not found")

    try:
        maybe = authorize(row)
        if inspect.isawaitable(maybe):
            await maybe
    except UnauthorizedDownload:
        raise
    except Exception as exc:  # any authorize failure denies (fail-closed)
        raise UnauthorizedDownload(str(exc)) from exc

    if row.scan_status != "clean":
        raise DownloadNotReady(f"scan_status={row.scan_status}")
    if row.disposed_at is not None:
        raise DownloadNotReady("attachment bytes have been disposed")

    served_key = row.sanitized_sha256 or row.sha256
    return AttachmentDownload(
        filename=row.original_filename,
        content_type=row.sanitized_mime or row.sniffed_mime,
        size=row.sanitized_byte_size or row.byte_size,
        sha256=served_key,
        stream=storage.open(served_key),
    )


async def soft_delete_attachment(
    session: AsyncSession, attachment_id: int, *, actor_id: int | None = None
) -> None:
    """Soft-delete the reference row. Does NOT touch the stored bytes (retention)."""
    row = (
        await session.execute(select(Attachment).where(Attachment.id == attachment_id))
    ).scalar_one_or_none()
    if row is None:
        raise AttachmentNotFound(f"attachment {attachment_id} not found")
    soft_delete(row, actor_id=actor_id)


async def disposal_eligibility_report(
    session: AsyncSession, *, as_of: datetime | None = None
) -> list[retention.DisposalCandidate]:
    """List every attachment's disposal eligibility (including soft-deleted rows —
    disposition is orthogonal to soft delete). Never deletes anything."""
    rows = (
        await session.execute(
            select(Attachment).execution_options(include_deleted=True)
        )
    ).scalars()
    return [retention.evaluate_candidate(row, as_of=as_of) for row in rows]
