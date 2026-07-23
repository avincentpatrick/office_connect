"""Storage driver interface (core-service #2 seam; plan S-5).

One interface, two drivers: a local content-addressed volume store (the on-prem
production default, master-plan §4 #3) and Google Drive (kept for tenants that
want it). Modules never touch a driver directly — the Increment-4 attachments
service (`core_attachments`) will own the upload pipeline (magic-byte allowlist,
ClamAV, Pillow re-encode, retention/`legal_hold`) and call this seam.

Content addressing: ``save`` returns the SHA-256 of the bytes as the object
``key``. Identical content dedups to one stored object. ``key`` is opaque to
callers — never a path. ``delete`` is *physical* file removal, invoked only by
the attachments/retention layer, never by a business row (soft deletes and the
no-hard-delete rule are about DB rows; blob GC is a separate, deliberate action).
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import BinaryIO

# Objects are keyed by the hex SHA-256 of their content.
KEY_LENGTH = 64


class StorageError(RuntimeError):
    """Raised for any storage-driver failure (config, I/O, or remote API)."""


@dataclass(frozen=True)
class StoredObject:
    """A handle to a stored blob. ``key`` is the content SHA-256 (hex)."""

    key: str
    size: int
    content_type: str
    # Driver-specific locator (a path for local, a file id for Drive) — for
    # diagnostics/logging only; callers address objects by ``key``.
    backend_ref: str | None = None


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class StorageDriver(ABC):
    """Content-addressed blob store. Implementations must be import-safe:
    build any remote client lazily (never at construction) so importing the
    module needs no credentials."""

    name: str = "base"

    @abstractmethod
    def save(
        self, data: bytes, *, content_type: str, filename: str | None = None
    ) -> StoredObject:
        """Store ``data`` and return its handle. Idempotent by content: saving
        the same bytes twice yields the same ``key`` and stores once."""

    @abstractmethod
    def open(self, key: str) -> BinaryIO:
        """Open a stored object for streaming reads. Raises ``StorageError`` if
        the key is absent."""

    def read(self, key: str) -> bytes:
        """Read a whole object into memory (convenience over ``open``)."""
        with self.open(key) as fh:
            return fh.read()

    @abstractmethod
    def exists(self, key: str) -> bool:
        """True if an object with ``key`` is present."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Physically remove an object. Idempotent (absent key is not an error).
        Reserved for the attachments/retention layer — not for business rows."""

    @staticmethod
    def _validate_key(key: str) -> str:
        """Guard against path traversal / malformed keys — a content key is
        always 64 lowercase hex chars."""
        if len(key) != KEY_LENGTH or any(c not in "0123456789abcdef" for c in key):
            raise StorageError(f"invalid storage key {key!r}")
        return key
