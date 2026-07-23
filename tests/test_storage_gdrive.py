"""QA gate: Google Drive storage driver (Increment 3) — google client mocked.

No real credentials in dev: the driver's built API client is replaced with a
MagicMock so we exercise the Shared-Drive verification (S-5), content-addressed
dedup, upload, and delete logic without touching Google.
"""

from unittest.mock import MagicMock

import pytest

from office_connect.core.config import Settings
from office_connect.core.storage import StorageError, get_storage_driver, sha256_hex
from office_connect.core.storage.gdrive import GoogleDriveStorageDriver


def _driver(svc) -> GoogleDriveStorageDriver:
    d = GoogleDriveStorageDriver(
        Settings(google_credentials_path="/fake.json", gdrive_folder_id="folder123")
    )
    d._svc = svc  # inject the mocked API client (skips creds/build)
    return d


def _files(svc) -> MagicMock:
    return svc.files.return_value


def test_verify_requires_shared_drive():
    svc = MagicMock()
    _files(svc).get.return_value.execute.return_value = {"id": "folder123"}  # no driveId
    driver = _driver(svc)
    with pytest.raises(StorageError, match="Shared Drive"):
        driver._verify_shared_drive()


def test_save_uploads_when_absent():
    svc = MagicMock()
    _files(svc).get.return_value.execute.return_value = {"id": "folder123", "driveId": "d1"}
    _files(svc).list.return_value.execute.return_value = {"files": []}  # not found
    _files(svc).create.return_value.execute.return_value = {"id": "fileABC", "size": "5"}

    driver = _driver(svc)
    data = b"hello"
    stored = driver.save(data, content_type="text/plain", filename="h.txt")

    assert stored.key == sha256_hex(data)
    assert stored.backend_ref == "fileABC"
    # supportsAllDrives must be set on the create call (Shared Drive requirement).
    _, create_kwargs = _files(svc).create.call_args
    assert create_kwargs["supportsAllDrives"] is True
    assert create_kwargs["body"]["name"] == stored.key


def test_save_dedups_when_present():
    svc = MagicMock()
    _files(svc).get.return_value.execute.return_value = {"id": "folder123", "driveId": "d1"}
    _files(svc).list.return_value.execute.return_value = {
        "files": [{"id": "existing", "name": "k", "size": "5"}]
    }
    driver = _driver(svc)
    stored = driver.save(b"hello", content_type="text/plain")
    assert stored.backend_ref == "existing"
    _files(svc).create.assert_not_called()  # dedup: no upload


def test_exists_and_delete():
    svc = MagicMock()
    _files(svc).list.return_value.execute.return_value = {
        "files": [{"id": "existing", "name": "k"}]
    }
    driver = _driver(svc)
    key = sha256_hex(b"z")
    assert driver.exists(key) is True
    driver.delete(key)
    _files(svc).delete.assert_called_once()


def test_factory_selects_gdrive():
    driver = get_storage_driver(
        Settings(storage_driver="gdrive", google_credentials_path="/x", gdrive_folder_id="f")
    )
    assert isinstance(driver, GoogleDriveStorageDriver)
