"""Increment 4 Group D — attachments service round-trip, fail-closed, retention.

Gate line: "attachment pipeline round-trip incl. fail-closed download
(infected/oversized/bad-type rejected)."
"""

from datetime import datetime, timedelta, timezone
from io import BytesIO

import pytest
from PIL import Image

from office_connect.core.attachments import service
from office_connect.core.attachments.errors import (
    AttachmentNotFound,
    DownloadNotReady,
    RejectedUpload,
    UnauthorizedDownload,
)
from office_connect.core.attachments.scanner import Scanner, ScanResult
from office_connect.core.config import Settings
from office_connect.core.storage.local import LocalVolumeStorageDriver


def _settings(tmp_path, **kw) -> Settings:
    return Settings(storage_dir=str(tmp_path), app_env="local", **kw)


def _jpeg_with_exif(color=(200, 30, 30)) -> bytes:
    img = Image.new("RGB", (16, 16), color)
    exif = img.getexif()
    exif[0x010E] = "SECRET location note"
    buf = BytesIO()
    img.save(buf, "JPEG", exif=exif.tobytes())
    return buf.getvalue()


class _CleanScanner(Scanner):
    name = "test-clean"

    def scan(self, data):
        return ScanResult("clean", None, "test-clean")


class _InfectedScanner(Scanner):
    name = "test-infected"

    def scan(self, data):
        return ScanResult("infected", "EICAR-Test", "test-infected")


def _allow(row):
    return None


def _deny(row):
    raise UnauthorizedDownload("not permitted")


async def test_round_trip_upload_scan_download(app_session, tmp_path):
    settings = _settings(tmp_path)
    storage = LocalVolumeStorageDriver(settings)
    up = await service.upload_attachment(
        app_session,
        _jpeg_with_exif(),
        filename="photo.jpg",
        settings=settings,
        storage=storage,
    )
    await app_session.commit()
    assert up.scan_status == "pending"

    status = await service.process_attachment(
        app_session,
        up.attachment_id,
        scanner=_CleanScanner(),
        storage=storage,
        settings=settings,
    )
    await app_session.commit()
    assert status == "clean"

    dl = await service.download_attachment(
        app_session,
        up.attachment_id,
        authorize=_allow,
        storage=storage,
        settings=settings,
    )
    assert dl.content_type == "image/jpeg"
    body = dl.stream.read()
    dl.stream.close()
    # The served copy is the sanitized derivative — no EXIF survives.
    assert dict(Image.open(BytesIO(body)).getexif()) == {}


async def test_pending_download_is_denied(app_session, tmp_path):
    settings = _settings(tmp_path)
    storage = LocalVolumeStorageDriver(settings)
    up = await service.upload_attachment(
        app_session, _jpeg_with_exif(), filename="p.jpg", settings=settings, storage=storage
    )
    await app_session.commit()
    with pytest.raises(DownloadNotReady):
        await service.download_attachment(
            app_session, up.attachment_id, authorize=_allow, storage=storage, settings=settings
        )


async def test_infected_download_is_denied(app_session, tmp_path):
    settings = _settings(tmp_path)
    storage = LocalVolumeStorageDriver(settings)
    up = await service.upload_attachment(
        app_session, _jpeg_with_exif(), filename="v.jpg", settings=settings, storage=storage
    )
    await app_session.commit()
    status = await service.process_attachment(
        app_session, up.attachment_id, scanner=_InfectedScanner(), storage=storage, settings=settings
    )
    await app_session.commit()
    assert status == "infected"
    with pytest.raises(DownloadNotReady):
        await service.download_attachment(
            app_session, up.attachment_id, authorize=_allow, storage=storage, settings=settings
        )


async def test_bad_type_and_oversized_rejected(app_session, tmp_path):
    settings = _settings(tmp_path)
    storage = LocalVolumeStorageDriver(settings)
    with pytest.raises(RejectedUpload):
        await service.upload_attachment(
            app_session, b"just text, not a file", filename="x.txt", settings=settings, storage=storage
        )
    small = _settings(tmp_path, attachment_max_bytes=10)
    with pytest.raises(RejectedUpload):
        await service.upload_attachment(
            app_session, _jpeg_with_exif(), filename="big.jpg", settings=small, storage=storage
        )


async def test_authorize_hook_denies(app_session, tmp_path):
    settings = _settings(tmp_path)
    storage = LocalVolumeStorageDriver(settings)
    up = await service.upload_attachment(
        app_session, _jpeg_with_exif(), filename="a.jpg", settings=settings, storage=storage
    )
    await service.process_attachment(
        app_session, up.attachment_id, scanner=_CleanScanner(), storage=storage, settings=settings
    )
    await app_session.commit()
    with pytest.raises(UnauthorizedDownload):
        await service.download_attachment(
            app_session, up.attachment_id, authorize=_deny, storage=storage, settings=settings
        )


async def test_dedup_one_blob_two_rows(app_session, tmp_path):
    settings = _settings(tmp_path)
    storage = LocalVolumeStorageDriver(settings)
    data = _jpeg_with_exif(color=(1, 2, 3))
    a = await service.upload_attachment(
        app_session, data, filename="d1.jpg", settings=settings, storage=storage
    )
    b = await service.upload_attachment(
        app_session, data, filename="d2.jpg", settings=settings, storage=storage
    )
    await app_session.commit()
    assert a.attachment_id != b.attachment_id
    assert a.sha256 == b.sha256
    assert b.deduped is True
    blobs = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert len(blobs) == 1  # one physical object for two references


async def test_soft_delete_keeps_blob(app_session, tmp_path):
    settings = _settings(tmp_path)
    storage = LocalVolumeStorageDriver(settings)
    up = await service.upload_attachment(
        app_session, _jpeg_with_exif(color=(9, 9, 9)), filename="s.jpg", settings=settings, storage=storage
    )
    await app_session.commit()
    await service.soft_delete_attachment(app_session, up.attachment_id)
    await app_session.commit()

    # The reference is gone…
    with pytest.raises(AttachmentNotFound):
        await service.download_attachment(
            app_session, up.attachment_id, authorize=_allow, storage=storage, settings=settings
        )
    # …but the bytes remain (soft delete != records disposition).
    assert storage.exists(up.sha256) is True


async def test_disposal_eligibility_report(app_session, tmp_path):
    settings = _settings(tmp_path)
    storage = LocalVolumeStorageDriver(settings)
    long_ago = datetime(2000, 1, 1, tzinfo=timezone.utc)

    eligible = await service.upload_attachment(
        app_session, _jpeg_with_exif(color=(11, 0, 0)), filename="e.jpg",
        retention_starts_at=long_ago, settings=settings, storage=storage
    )
    held = await service.upload_attachment(
        app_session, _jpeg_with_exif(color=(0, 11, 0)), filename="h.jpg",
        retention_starts_at=long_ago, settings=settings, storage=storage
    )
    await app_session.commit()

    # Put the second under legal hold and soft-delete it (still reportable).
    from sqlalchemy import select
    from office_connect.core.models import Attachment
    held_row = (
        await app_session.execute(select(Attachment).where(Attachment.id == held.attachment_id))
    ).scalar_one()
    held_row.legal_hold = True
    await app_session.commit()
    await service.soft_delete_attachment(app_session, held.attachment_id)
    await app_session.commit()

    report = await service.disposal_eligibility_report(
        app_session, as_of=datetime(2026, 1, 1, tzinfo=timezone.utc)
    )
    by_id = {c.attachment_id: c for c in report}
    assert by_id[eligible.attachment_id].eligible is True
    # legal_hold blocks disposal, and the soft-deleted row STILL appears.
    assert held.attachment_id in by_id
    assert by_id[held.attachment_id].eligible is False
    assert by_id[held.attachment_id].legal_hold is True
