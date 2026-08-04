"""Attachments — the one content-addressed file service every module consumes.

Master-plan §1.1 #2. Upload pipeline: stream cap → magic-byte allowlist
(JPEG/PNG/WebP/PDF; HEIC→JPEG; never SVG) → SHA-256 → content-addressed store
(the Increment-3 ``StorageDriver`` seam) → ClamAV scan (fail-closed) → Pillow
re-encode/EXIF-strip. Downloads are auth-checked and streaming only (Stage B
adds the HTTP router; the service takes an ``authorize`` hook now).

Key design points:
- ``(holder_kind, holder_id)`` is the **sanctioned polymorphic reference** (no FK)
  — a module resolves authorization through the entity named by ``holder_kind``.
- ``sha256`` = the original received bytes (immutable evidence, dedup key, the
  thing ClamAV scans). ``sanitized_sha256`` = the re-encoded/EXIF-stripped
  derivative served for images; download serves it when present, else ``sha256``.
- ``sha256`` is **indexed but not unique** — dedup is a storage-layer property;
  each reference is its own row and live rows legitimately share a blob.
- Retention: ``retention_class`` / ``retention_starts_at`` / ``legal_hold`` — soft
  delete is NOT records disposition; **no automated purge ever** (database-
  standards §8). Physical blob delete happens only via a human disposal action.
"""

from datetime import datetime

from sqlalchemy import BigInteger, Enum, ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from office_connect.core.base import (
    AuditColsMixin,
    Base,
    PKMixin,
    SoftDeleteMixin,
)

ScanStatus = Enum(
    "pending", "clean", "infected", "error", name="core_attachment_scan_status"
)

# Where the bytes came from (R-5). 'uploaded' = a human sent them and they are
# untrusted; 'generated' = this platform rendered them from its own templates.
# The distinction is load-bearing three times over — see the column comment.
AttachmentOrigin = Enum("uploaded", "generated", name="core_attachment_origin")


class Attachment(PKMixin, AuditColsMixin, SoftDeleteMixin, Base):
    __tablename__ = "core_attachments"
    __table_args__ = (
        Index(
            "ix_core_attachments_holder", "holder_kind", "holder_id"
        ),
        Index("ix_core_attachments_scan_status", "scan_status"),
        # NON-unique on purpose — many references share one content blob.
        Index("ix_core_attachments_sha256", "sha256"),
        Index(
            "ix_core_attachments_legal_hold",
            "legal_hold",
            postgresql_where=text("legal_hold"),
        ),
        Index("ix_core_attachments_retention_starts_at", "retention_starts_at"),
        Index("ix_core_attachments_created_by", "created_by"),
    )

    # Polymorphic owner (no FK — sanctioned exception, database-standards §3).
    holder_kind: Mapped[str | None]
    holder_id: Mapped[int | None] = mapped_column(BigInteger)

    original_filename: Mapped[str]
    sniffed_mime: Mapped[str]  # authoritative type from magic bytes
    declared_mime: Mapped[str | None]  # client Content-Type — forensics only
    byte_size: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str]  # = storage key of the ORIGINAL bytes (audited evidence)
    storage_backend: Mapped[str]  # 'local' | 'gdrive' — which driver holds the blob
    media_kind: Mapped[str]  # 'image' | 'pdf'

    # Provenance (R-5, core-service #8). Decides three things that would each
    # otherwise need their own flag:
    #  1. SCAN — 'generated' bytes are produced in-process from autoescaped
    #     templates and never leave it, so they are born 'clean'. Scanning our
    #     own renderer's output is theatre, and in prod NullScanner returns
    #     'error', which would make every generated packet permanently
    #     undownloadable whenever ClamAV is absent.
    #  2. DISPOSITION — only 'generated' PDFs may be served inline for preview.
    #     An uploaded PDF can carry JavaScript, so uploads stay `attachment`
    #     forever. Derived server-side; never client-controlled.
    #  3. COUNTING — a consumer's evidence tally filters on 'uploaded', so a
    #     generated document is never miscounted as evidence a human supplied.
    origin: Mapped[str] = mapped_column(AttachmentOrigin, server_default="uploaded")

    # Sanitized derivative (images only; NULL for PDF and until re-encode runs).
    sanitized_sha256: Mapped[str | None]
    sanitized_mime: Mapped[str | None]
    sanitized_byte_size: Mapped[int | None] = mapped_column(BigInteger)
    sanitized_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    # Fail-closed scan state machine.
    scan_status: Mapped[str] = mapped_column(ScanStatus, server_default="pending")
    scan_signature: Mapped[str | None]
    scanned_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    scanner_name: Mapped[str | None]

    # Retention (NAP/GRDS) — no auto-purge ever.
    retention_class: Mapped[str] = mapped_column(server_default="default")
    retention_starts_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True)
    )
    legal_hold: Mapped[bool] = mapped_column(server_default=text("false"))
    disposed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    disposed_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("core_users.id")
    )
    disposal_authority: Mapped[str | None]
