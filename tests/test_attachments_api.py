"""Stage B (Phase 2) Increment 4 — authed attachments HTTP router.

End-to-end over the ASGI ``client`` (real Postgres + Redis db 4, cookie sessions):
upload/download gated by ``require_permission``, per-upload scan enqueue after
commit, error→status mapping, and soft-delete. Mirrors ``test_rbac_enforcement.py``
(login + CSRF) and ``test_attachments_service.py`` (real JPEG bytes).
"""

from io import BytesIO

import pyotp
from PIL import Image
from sqlalchemy import select

from office_connect.core.attachments import service
from office_connect.core.config import Settings
from office_connect.core.models import Attachment

CSRF = {"X-Requested-With": "1"}


def _jpeg(color=(10, 120, 200)) -> bytes:
    img = Image.new("RGB", (16, 16), color)
    exif = img.getexif()
    exif[0x010E] = "SECRET camera note"
    buf = BytesIO()
    img.save(buf, "JPEG", exif=exif.tobytes())
    return buf.getvalue()


def _upload_files(name: str = "photo.jpg", ctype: str = "image/jpeg"):
    return {"file": (name, _jpeg(), ctype)}


async def _login(client, user, pw, mfa_secret=None):
    r = await client.post(
        "/api/v1/auth/login",
        json={"identifier": user.email, "password": pw},
        headers=CSRF,
    )
    if r.json().get("status") == "mfa_required":
        r = await client.post(
            "/api/v1/auth/mfa/verify",
            json={
                "mfa_token": r.json()["mfa_token"],
                "code": pyotp.TOTP(mfa_secret).now(),
            },
            headers=CSRF,
        )
    return r


async def test_upload_requires_permission(client, make_user, session_redis, seed_rbac):
    user, pw = await make_user()  # no roles → no attachment.upload
    await _login(client, user, pw)
    r = await client.post("/api/v1/attachments", files=_upload_files(), headers=CSRF)
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"


async def test_upload_missing_csrf_rejected(client, make_user, session_redis, seed_rbac):
    user, pw = await make_user(roles=("staff",))
    await _login(client, user, pw)
    r = await client.post("/api/v1/attachments", files=_upload_files())  # no CSRF hdr
    assert r.status_code == 403 and r.json()["error"]["code"] == "csrf_failed"


async def test_upload_creates_pending_row(
    client, make_user, session_redis, seed_rbac, app_session, no_scan_worker
):
    user, pw = await make_user(roles=("staff",))
    await _login(client, user, pw)
    r = await client.post("/api/v1/attachments", files=_upload_files(), headers=CSRF)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["scan_status"] == "pending"
    assert body["media_kind"] == "image"
    row = (
        await app_session.execute(
            select(Attachment).where(Attachment.id == body["id"])
        )
    ).scalar_one()
    assert row.created_by == user.id


async def test_upload_bad_type_rejected(client, make_user, session_redis, seed_rbac):
    user, pw = await make_user(roles=("staff",))
    await _login(client, user, pw)
    r = await client.post(
        "/api/v1/attachments",
        files={"file": ("notes.txt", b"just text, not an image", "text/plain")},
        headers=CSRF,
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "attachment_rejected"


async def test_upload_oversized_rejected(
    client, make_user, session_redis, seed_rbac, monkeypatch
):
    # Shrink the cap via the router's settings lookup so a tiny file trips the guard.
    monkeypatch.setattr(
        "office_connect.core.api.attachments.get_settings",
        lambda: Settings(attachment_max_bytes=10, app_env="local"),
    )
    user, pw = await make_user(roles=("staff",))
    await _login(client, user, pw)
    r = await client.post("/api/v1/attachments", files=_upload_files(), headers=CSRF)
    assert r.status_code == 413 and r.json()["error"]["code"] == "payload_too_large"


async def test_upload_enqueues_scan_after_commit(
    client, make_user, session_redis, seed_rbac
):
    from office_connect.core.attachments import scan_queue

    captured: list[int] = []
    previous = scan_queue._enqueuer
    scan_queue.register_enqueuer(captured.append)
    try:
        user, pw = await make_user(roles=("staff",))
        await _login(client, user, pw)
        r = await client.post(
            "/api/v1/attachments", files=_upload_files(), headers=CSRF
        )
        assert r.status_code == 201
        assert captured == [r.json()["id"]]  # enqueued exactly once, after commit
    finally:
        scan_queue._enqueuer = previous


async def test_metadata_read_and_not_found(
    client, make_user, session_redis, seed_rbac, no_scan_worker
):
    user, pw = await make_user(roles=("staff",))
    await _login(client, user, pw)
    up = await client.post("/api/v1/attachments", files=_upload_files(), headers=CSRF)
    aid = up.json()["id"]
    got = await client.get(f"/api/v1/attachments/{aid}")
    assert got.status_code == 200 and got.json()["scan_status"] == "pending"
    missing = await client.get("/api/v1/attachments/999999999")
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "not_found"


async def test_download_pending_returns_409(
    client, make_user, session_redis, seed_rbac, no_scan_worker
):
    user, pw = await make_user(roles=("staff",))
    await _login(client, user, pw)
    up = await client.post("/api/v1/attachments", files=_upload_files(), headers=CSRF)
    aid = up.json()["id"]
    r = await client.get(f"/api/v1/attachments/{aid}/content")
    assert r.status_code == 409 and r.json()["error"]["code"] == "attachment_not_ready"


async def test_download_clean_streams_sanitized(
    client, make_user, session_redis, seed_rbac, app_session
):
    user, pw = await make_user(roles=("staff",))
    await _login(client, user, pw)
    up = await client.post("/api/v1/attachments", files=_upload_files(), headers=CSRF)
    aid = up.json()["id"]
    # Drive the scan/re-encode (default NullScanner is clean in dev) as the worker would.
    status = await service.process_attachment(app_session, aid)
    await app_session.commit()
    assert status == "clean"

    r = await client.get(f"/api/v1/attachments/{aid}/content")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/")
    assert "attachment" in r.headers["content-disposition"]
    # The served copy is the sanitized derivative — EXIF stripped.
    assert dict(Image.open(BytesIO(r.content)).getexif()) == {}


async def test_download_forbidden_without_permission(
    client, make_user, session_redis, seed_rbac
):
    owner, opw = await make_user(roles=("staff",))
    await _login(client, owner, opw)
    up = await client.post("/api/v1/attachments", files=_upload_files(), headers=CSRF)
    aid = up.json()["id"]

    auditor, apw = await make_user(roles=("auditor",))  # read + dispose, NOT download
    await _login(client, auditor, apw)
    r = await client.get(f"/api/v1/attachments/{aid}/content")
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"


async def test_disposal_report_requires_permission(
    client, make_user, session_redis, seed_rbac
):
    auditor, apw = await make_user(roles=("auditor",))  # holds attachment.dispose.read
    await _login(client, auditor, apw)
    ok = await client.get("/api/v1/attachments/disposal-report")
    assert ok.status_code == 200 and "candidates" in ok.json()

    staff, spw = await make_user(roles=("staff",))  # no dispose.read
    await _login(client, staff, spw)
    denied = await client.get("/api/v1/attachments/disposal-report")
    assert denied.status_code == 403 and denied.json()["error"]["code"] == "forbidden"


async def test_delete_soft_deletes_and_blocks_download(
    client, make_user, session_redis, seed_rbac
):
    secret = pyotp.random_base32()
    admin, pw = await make_user(
        roles=("system_admin",), mfa_enabled=True, mfa_secret=secret
    )
    login = await _login(client, admin, pw, secret)
    assert login.json()["status"] == "authenticated"

    up = await client.post("/api/v1/attachments", files=_upload_files(), headers=CSRF)
    aid = up.json()["id"]
    d = await client.delete(f"/api/v1/attachments/{aid}", headers=CSRF)
    assert d.status_code == 200
    # Soft-deleted rows are filtered out → read + download both 404.
    assert (await client.get(f"/api/v1/attachments/{aid}")).status_code == 404
    assert (
        await client.get(f"/api/v1/attachments/{aid}/content")
    ).status_code == 404
