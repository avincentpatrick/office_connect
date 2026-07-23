"""Core attachments service (core-service #2) — Increment 4.

Public API: the service functions plus the scanner seam and errors. Modules call
``upload_attachment`` / ``download_attachment`` (never a storage driver directly).
"""

from office_connect.core.attachments.errors import (
    AttachmentError,
    AttachmentNotFound,
    DownloadNotReady,
    RejectedUpload,
    UnauthorizedDownload,
)
from office_connect.core.attachments.retention import (
    RETENTION_CLASSES,
    DisposalCandidate,
    retain_until,
)
from office_connect.core.attachments.scanner import (
    ClamAVScanner,
    NullScanner,
    ScanResult,
    Scanner,
    get_scanner,
)
from office_connect.core.attachments.service import (
    AttachmentDownload,
    UploadResult,
    disposal_eligibility_report,
    download_attachment,
    process_attachment,
    soft_delete_attachment,
    upload_attachment,
)

__all__ = [
    "AttachmentError",
    "AttachmentNotFound",
    "DownloadNotReady",
    "RejectedUpload",
    "UnauthorizedDownload",
    "RETENTION_CLASSES",
    "DisposalCandidate",
    "retain_until",
    "ClamAVScanner",
    "NullScanner",
    "ScanResult",
    "Scanner",
    "get_scanner",
    "AttachmentDownload",
    "UploadResult",
    "disposal_eligibility_report",
    "download_attachment",
    "process_attachment",
    "soft_delete_attachment",
    "upload_attachment",
]
