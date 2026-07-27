"""Attachment endpoint request/response models (api-standards §2).

Response models are built field-by-field from the ORM row; internal columns
(``sanitized_sha256``, storage keys, scanner internals) are deliberately not
exposed.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AttachmentSummary(BaseModel):
    id: int
    original_filename: str
    sniffed_mime: str
    media_kind: str
    byte_size: int
    sha256: str  # the original-bytes content address (audited evidence)
    scan_status: str
    scanned_at: datetime | None = None
    holder_kind: str | None = None
    holder_id: int | None = None
    retention_class: str
    legal_hold: bool
    disposed_at: datetime | None = None
    created_at: datetime
    created_by: int | None = None
    deduped: bool | None = None  # set only on the upload response


class DisposalCandidateResponse(BaseModel):
    attachment_id: int
    sha256: str
    retention_class: str
    retention_starts_at: datetime | None = None
    retain_until: datetime | None = None
    legal_hold: bool
    eligible: bool
    reason: str


class DisposalReportResponse(BaseModel):
    candidates: list[DisposalCandidateResponse]
