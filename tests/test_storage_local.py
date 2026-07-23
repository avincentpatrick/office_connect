"""QA gate: local-volume storage driver round-trip (Increment 3).

Pure unit tests against a tmp dir — no DB. The local driver is the on-prem
production default; this is the acceptance round-trip.
"""

import pytest

from office_connect.core.config import Settings
from office_connect.core.storage import StorageError, get_storage_driver, sha256_hex
from office_connect.core.storage.local import LocalVolumeStorageDriver


def _driver(tmp_path) -> LocalVolumeStorageDriver:
    return LocalVolumeStorageDriver(Settings(storage_dir=str(tmp_path)))


def test_save_read_round_trip(tmp_path):
    driver = _driver(tmp_path)
    data = b"local travel reimbursement receipt \xe2\x9c\x93"
    stored = driver.save(data, content_type="application/pdf", filename="or.pdf")

    assert stored.key == sha256_hex(data)  # content-addressed
    assert stored.size == len(data)
    assert stored.content_type == "application/pdf"
    assert driver.exists(stored.key)
    assert driver.read(stored.key) == data  # byte-identical round-trip


def test_content_addressed_dedup(tmp_path):
    driver = _driver(tmp_path)
    data = b"same bytes"
    first = driver.save(data, content_type="text/plain")
    second = driver.save(data, content_type="text/plain")
    assert first.key == second.key
    # Only one blob on disk under the sharded path.
    blobs = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert len(blobs) == 1


def test_delete_is_idempotent(tmp_path):
    driver = _driver(tmp_path)
    stored = driver.save(b"x", content_type="text/plain")
    driver.delete(stored.key)
    assert not driver.exists(stored.key)
    driver.delete(stored.key)  # absent key is not an error


def test_missing_key_raises(tmp_path):
    driver = _driver(tmp_path)
    absent = sha256_hex(b"never stored")
    with pytest.raises(StorageError):
        driver.open(absent)


def test_malformed_key_rejected(tmp_path):
    driver = _driver(tmp_path)
    with pytest.raises(StorageError):
        driver.exists("../etc/passwd")


def test_factory_selects_local(tmp_path):
    driver = get_storage_driver(Settings(storage_driver="local", storage_dir=str(tmp_path)))
    assert isinstance(driver, LocalVolumeStorageDriver)


def test_factory_unknown_driver_raises(tmp_path):
    with pytest.raises(StorageError):
        get_storage_driver(Settings(storage_driver="nope", storage_dir=str(tmp_path)))
