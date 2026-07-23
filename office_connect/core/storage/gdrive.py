"""Google Drive storage driver (kept for tenants that want it; plan S-5).

Uploads to a configured **Shared Drive** folder using a service account. The
Drive client and google libraries are imported lazily inside ``_service`` so
importing this module needs neither the packages nor credentials — the local
driver is the default and must not pay for Google being installed.

Content addressing on Drive: the object ``key`` (content SHA-256) is the Drive
file *name* within the folder, and is also recorded in ``appProperties`` so a
lookup is a single ``files.list`` by name. Uploading identical content twice
finds the existing file and dedups.

**Shared-Drive verification (S-5):** before the first write the driver confirms
``gdrive_folder_id`` resolves to a folder that lives on a Shared Drive (it has a
``driveId``); a personal *My Drive* folder is refused, because service-account
uploads to My Drive are unowned/unquota'd and effectively unrecoverable.
"""

from __future__ import annotations

import io
from typing import BinaryIO

from office_connect.core.config import Settings, get_settings
from office_connect.core.storage.base import (
    StorageDriver,
    StorageError,
    StoredObject,
    sha256_hex,
)

# Read/write files this service account created; enough to upload + fetch.
_SCOPES = ["https://www.googleapis.com/auth/drive.file"]


class GoogleDriveStorageDriver(StorageDriver):
    name = "gdrive"

    def __init__(self, settings: Settings | None = None) -> None:
        settings = settings or get_settings()
        self._creds_path = settings.google_credentials_path
        self._folder_id = settings.gdrive_folder_id
        self._svc = None  # lazily built google API client
        self._drive_verified = False

    # -- lazy client -------------------------------------------------------
    def _service(self):
        if self._svc is not None:
            return self._svc
        if not self._creds_path:
            raise StorageError("gdrive storage needs GOOGLE_CREDENTIALS_PATH")
        if not self._folder_id:
            raise StorageError("gdrive storage needs GDRIVE_FOLDER_ID")
        try:
            from google.oauth2 import service_account  # noqa: PLC0415
            from googleapiclient.discovery import build  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover - deps ship in the image
            raise StorageError(
                "gdrive storage requires google-api-python-client + google-auth"
            ) from exc
        creds = service_account.Credentials.from_service_account_file(
            self._creds_path, scopes=_SCOPES
        )
        self._svc = build("drive", "v3", credentials=creds, cache_discovery=False)
        return self._svc

    def _verify_shared_drive(self) -> None:
        """Confirm the target folder lives on a Shared Drive (S-5)."""
        if self._drive_verified:
            return
        svc = self._service()
        try:
            meta = (
                svc.files()
                .get(fileId=self._folder_id, fields="id,driveId,mimeType",
                     supportsAllDrives=True)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001 - surface as StorageError
            raise StorageError(f"gdrive folder not reachable: {exc}") from exc
        if not meta.get("driveId"):
            raise StorageError(
                "GDRIVE_FOLDER_ID is not on a Shared Drive; refusing My Drive "
                "uploads (service-account files there are unrecoverable)"
            )
        self._drive_verified = True

    def _find(self, key: str) -> dict | None:
        svc = self._service()
        key = self._validate_key(key)
        resp = (
            svc.files()
            .list(
                q=f"name = '{key}' and '{self._folder_id}' in parents and trashed = false",
                spaces="drive",
                fields="files(id,name,size)",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                pageSize=1,
            )
            .execute()
        )
        files = resp.get("files", [])
        return files[0] if files else None

    # -- StorageDriver -----------------------------------------------------
    def save(
        self, data: bytes, *, content_type: str, filename: str | None = None
    ) -> StoredObject:
        from googleapiclient.http import MediaIoBaseUpload  # noqa: PLC0415

        self._verify_shared_drive()
        key = sha256_hex(data)
        existing = self._find(key)
        if existing is not None:  # content-addressed dedup
            return StoredObject(
                key=key,
                size=int(existing.get("size") or len(data)),
                content_type=content_type,
                backend_ref=existing["id"],
            )
        svc = self._service()
        media = MediaIoBaseUpload(io.BytesIO(data), mimetype=content_type, resumable=False)
        body = {
            "name": key,
            "parents": [self._folder_id],
            "appProperties": {"sha256": key, "original_filename": filename or ""},
        }
        try:
            created = (
                svc.files()
                .create(body=body, media_body=media, fields="id,size",
                        supportsAllDrives=True)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            raise StorageError(f"gdrive upload failed: {exc}") from exc
        return StoredObject(
            key=key, size=len(data), content_type=content_type,
            backend_ref=created["id"],
        )

    def open(self, key: str) -> BinaryIO:
        from googleapiclient.http import MediaIoBaseDownload  # noqa: PLC0415

        found = self._find(key)
        if found is None:
            raise StorageError(f"object not found: {key}")
        svc = self._service()
        buf = io.BytesIO()
        request = svc.files().get_media(fileId=found["id"], supportsAllDrives=True)
        downloader = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        buf.seek(0)
        return buf

    def exists(self, key: str) -> bool:
        return self._find(key) is not None

    def delete(self, key: str) -> None:
        found = self._find(key)
        if found is None:
            return
        svc = self._service()
        svc.files().delete(fileId=found["id"], supportsAllDrives=True).execute()
