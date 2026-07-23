"""Storage drivers (core-service #2 seam; plan S-5).

``get_storage_driver()`` returns the configured driver — local content-addressed
volume (default) or Google Drive. Import the interface types from here; concrete
drivers are built lazily so importing this package needs no credentials.
"""

from __future__ import annotations

from office_connect.core.config import Settings, get_settings
from office_connect.core.storage.base import (
    StorageDriver,
    StorageError,
    StoredObject,
    sha256_hex,
)

__all__ = [
    "StorageDriver",
    "StorageError",
    "StoredObject",
    "sha256_hex",
    "get_storage_driver",
]


def get_storage_driver(settings: Settings | None = None) -> StorageDriver:
    """Build the driver named by ``settings.storage_driver`` ('local'|'gdrive')."""
    settings = settings or get_settings()
    driver = (settings.storage_driver or "local").lower()
    if driver == "local":
        from office_connect.core.storage.local import LocalVolumeStorageDriver

        return LocalVolumeStorageDriver(settings)
    if driver in ("gdrive", "google_drive", "drive"):
        from office_connect.core.storage.gdrive import GoogleDriveStorageDriver

        return GoogleDriveStorageDriver(settings)
    raise StorageError(f"unknown storage_driver {settings.storage_driver!r}")
