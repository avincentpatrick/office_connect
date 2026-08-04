"""Frozen document snapshots — core-service #3 (master-plan §1.1).

"Export → PDF → SHA-256 → snapshot + identity + timestamp; 'modified after
signature' re-flag." A snapshot is the assertion *this exact PDF was the
official version of this document, for this subject, at this moment, produced by
this person*. Signatures bind to snapshots, never to live data — which is the
whole point: re-rendering a Disbursement Voucher from current rows would
silently change the document an approver already signed.

Key design points:

- ``(subject_kind, subject_id)`` is the **sanctioned polymorphic reference** (no
  FK), the same convention ``core_attachments`` uses. Core must not hold a
  foreign key into a module table.
- ``content_sha256`` hashes the PDF **bytes** — tamper evidence.
  ``source_fingerprint`` hashes the canonical **context** that produced them —
  change detection. Both are needed and neither substitutes for the other: PDF
  bytes embed a creation timestamp, so identical data renders to different
  bytes, and hashing output could never answer "did the data change?".
- ``status`` is a lifecycle, not a boolean. ``superseded`` means a newer
  snapshot of the same document replaced it in the ordinary course;
  ``voided`` means it was invalidated because its inputs changed. Both keep the
  row (standing rule 6 — nothing is ever deleted), and the distinction is what
  an auditor reads to tell a routine reissue from an edit-after-the-fact.
- ``is_draft`` separates a pre-submit working copy (no reference number) from
  the filed original. A draft may be superseded freely; the official one being
  superseded is the event that re-flags signature steps.
"""

from datetime import datetime

from sqlalchemy import BigInteger, Enum, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from office_connect.core.base import (
    AuditColsMixin,
    Base,
    PKMixin,
    SoftDeleteMixin,
)

SnapshotStatus = Enum(
    "active", "superseded", "voided", name="core_document_snapshot_status"
)


class DocumentSnapshot(PKMixin, AuditColsMixin, SoftDeleteMixin, Base):
    __tablename__ = "core_document_snapshots"
    __table_args__ = (
        Index(
            "ix_core_document_snapshots_subject", "subject_kind", "subject_id"
        ),
        # The lookup every read does: "the live official copy of this document".
        Index(
            "ix_core_document_snapshots_active",
            "subject_kind",
            "subject_id",
            "document_key",
            postgresql_where=text("status = 'active' AND deleted_at IS NULL"),
        ),
        Index("ix_core_document_snapshots_attachment_id", "attachment_id"),
    )

    # Polymorphic subject (no FK — sanctioned exception, database-standards §3).
    subject_kind: Mapped[str]
    subject_id: Mapped[int] = mapped_column(BigInteger)

    # Namespaced registry key, e.g. 'reimb.iot45'.
    document_key: Mapped[str]
    attachment_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("core_attachments.id")
    )

    content_sha256: Mapped[str]  # hash of the PDF bytes — tamper evidence
    source_fingerprint: Mapped[str]  # hash of the render context — change detection

    # Workflow revision this was frozen against. The engine bumps revision_no on
    # every resubmit (workflow-standards §6), so a snapshot frozen at revision 1
    # is self-evidently stale once the claim is on revision 2.
    revision_no: Mapped[int | None]
    is_draft: Mapped[bool] = mapped_column(server_default=text("false"))

    status: Mapped[str] = mapped_column(SnapshotStatus, server_default="active")
    voided_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    voided_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("core_users.id")
    )
    void_reason: Mapped[str | None] = mapped_column(Text)

    # Identity + timestamp — the "signature" half of core-service #3.
    generated_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("core_users.id")
    )
    generated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
