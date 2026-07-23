"""Local content-addressed volume storage driver (production default).

Stores each blob once under ``<storage_dir>/<ab>/<cd>/<sha256>`` (two levels of
fan-out by the first hash bytes so no directory grows unbounded). Writes go to a
``.partial`` sibling and are atomically ``replace``d on success — a truncated
write never becomes a readable object (same discipline as ``ops/backup.py``).

The store is a bind-mounted host volume (``./storage`` → ``/app/storage``) so
blobs survive container rebuilds and are backed up with the host, matching the
on-prem posture (master-plan §4 #3).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import BinaryIO

from office_connect.core.config import Settings, get_settings
from office_connect.core.storage.base import (
    StorageDriver,
    StorageError,
    StoredObject,
    sha256_hex,
)


class LocalVolumeStorageDriver(StorageDriver):
    name = "local"

    def __init__(self, settings: Settings | None = None) -> None:
        settings = settings or get_settings()
        self._root = Path(settings.storage_dir)

    def _path_for(self, key: str) -> Path:
        key = self._validate_key(key)
        return self._root / key[:2] / key[2:4] / key

    def save(
        self, data: bytes, *, content_type: str, filename: str | None = None
    ) -> StoredObject:
        key = sha256_hex(data)
        target = self._path_for(key)
        if target.exists():  # content-addressed dedup: already stored
            return StoredObject(
                key=key,
                size=target.stat().st_size,
                content_type=content_type,
                backend_ref=str(target),
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        # Atomic publish: write to a temp file in the same dir, fsync, replace.
        fd, tmp_name = tempfile.mkstemp(dir=target.parent, suffix=".partial")
        tmp = Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            tmp.replace(target)  # atomic on the same filesystem
        except OSError as exc:
            tmp.unlink(missing_ok=True)
            raise StorageError(f"local storage write failed: {exc}") from exc
        return StoredObject(
            key=key, size=len(data), content_type=content_type, backend_ref=str(target)
        )

    def open(self, key: str) -> BinaryIO:
        path = self._path_for(key)
        try:
            return path.open("rb")
        except OSError as exc:
            raise StorageError(f"object not found: {key}") from exc

    def exists(self, key: str) -> bool:
        return self._path_for(key).exists()

    def delete(self, key: str) -> None:
        self._path_for(key).unlink(missing_ok=True)
