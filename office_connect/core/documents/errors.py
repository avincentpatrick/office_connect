"""Document-generation errors (core-service #8 / #3)."""

from __future__ import annotations


class DocumentError(RuntimeError):
    """Base class for document-generation failures."""


class UnknownDocument(DocumentError):
    """No document spec registered for that key."""


class RenderFailed(DocumentError):
    """The template or the PDF engine failed to produce bytes.

    Raised (rather than returning empty bytes) so the Celery task retries and,
    on final failure, leaves the checklist item un-generated — visibly not done
    — instead of storing a zero-byte PDF that would flip the item to Generated
    and lie to an approver.
    """


class SnapshotNotFound(DocumentError):
    """No live snapshot with that id."""
