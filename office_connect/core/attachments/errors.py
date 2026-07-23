"""Attachment service errors."""

from __future__ import annotations


class AttachmentError(RuntimeError):
    """Base class for attachment-service failures."""


class RejectedUpload(AttachmentError):
    """Upload failed validation (bad magic bytes, disallowed type, oversized)."""


class AttachmentNotFound(AttachmentError):
    """No live (non-soft-deleted) attachment with that id."""


class UnauthorizedDownload(AttachmentError):
    """The authorization hook rejected the download."""


class DownloadNotReady(AttachmentError):
    """The attachment is not servable (scan not clean, or bytes disposed)."""
