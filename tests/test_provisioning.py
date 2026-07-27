"""Stage B (Phase 2) Increment 4 — admin user provisioning.

End-to-end over the ASGI ``client``: create-from-staff (temp password, forced
change, not break-glass), permission gating, uniqueness conflicts, and
deactivation that revokes every Redis session + audits the acting admin.
"""

import uuid

import pyotp
from sqlalchemy import select

from office_connect.core.auth.password_policy import normalize_password
from office_connect.core.models import AuditLog, Staff, User
from office_connect.core.security import verify_password

CSRF = {"X-Requested-With": "1"}


def _tok() -> str:
    return uuid.uuid4().hex[:8]


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


async def _make_staff(app_session, *, email=None) -> Staff:
    tok = _tok()
    staff = Staff(
        employee_no=f"E-{tok}",
        given_name="Pat",
        surname="Reyes",
        full_name="Pat Reyes",
        email=email,
    )
    app_session.add(staff)
    await app_session.commit()
    await app_session.refresh(staff)
    return staff


async def _admin(make_user):
    secret = pyotp.random_base32()
    admin, pw = await make_user(
        roles=("system_admin",), mfa_enabled=True, mfa_secret=secret
    )
    return admin, pw, secret


async def test_create_requires_permission(client, make_user, session_redis, seed_rbac):
    staff_user, pw = await make_user(roles=("staff",))  # staff lacks user.create
    await _login(client, staff_user, pw)
    r = await client.post("/api/v1/users", json={"staff_id": 1}, headers=CSRF)
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"


async def test_create_from_staff(
    client, make_user, session_redis, seed_rbac, app_session
):
    admin, pw, secret = await _admin(make_user)
    staff = await _make_staff(app_session, email=f"{_tok()}@doh.gov")
    await _login(client, admin, pw, secret)

    r = await client.post(
        "/api/v1/users", json={"staff_id": staff.id}, headers=CSRF
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["email"] == staff.email
    temp = body["temporary_password"]

    user = (
        await app_session.execute(select(User).where(User.id == body["user_id"]))
    ).scalar_one()
    assert verify_password(normalize_password(temp), user.password_hash)
    assert user.must_change_password is True
    assert user.is_break_glass is False
    assert user.staff_id == staff.id

    events = (
        await app_session.execute(
            select(AuditLog).where(
                AuditLog.table_name == "core_users", AuditLog.row_pk == user.id
            )
        )
    ).scalars().all()
    assert any((e.new_data or {}).get("event") == "user.created" for e in events)


async def test_duplicate_staff_conflicts(
    client, make_user, session_redis, seed_rbac, app_session
):
    admin, pw, secret = await _admin(make_user)
    staff = await _make_staff(app_session, email=f"{_tok()}@doh.gov")
    await _login(client, admin, pw, secret)
    first = await client.post(
        "/api/v1/users", json={"staff_id": staff.id}, headers=CSRF
    )
    assert first.status_code == 201
    second = await client.post(
        "/api/v1/users", json={"staff_id": staff.id}, headers=CSRF
    )
    assert second.status_code == 409 and second.json()["error"]["code"] == "conflict"


async def test_email_required_when_staff_has_none(
    client, make_user, session_redis, seed_rbac, app_session
):
    admin, pw, secret = await _admin(make_user)
    staff = await _make_staff(app_session, email=None)
    await _login(client, admin, pw, secret)
    r = await client.post(
        "/api/v1/users", json={"staff_id": staff.id}, headers=CSRF
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


async def test_deactivate_revokes_sessions_and_audits(
    client, make_user, session_redis, session_store, seed_rbac, app_session
):
    admin, apw, secret = await _admin(make_user)
    target, tpw = await make_user()  # no roles

    # Target establishes a real db-4 session, then admin takes over the client.
    await _login(client, target, tpw)
    assert await session_store.list_for_user(target.id)  # has ≥1 live session
    await _login(client, admin, apw, secret)

    r = await client.post(
        f"/api/v1/users/{target.id}/deactivate", headers=CSRF
    )
    assert r.status_code == 200
    assert r.json()["sessions_revoked"] >= 1
    assert await session_store.list_for_user(target.id) == []  # all revoked now

    # target was created on app_session (identity map) — refresh past the stale copy.
    await app_session.refresh(target)
    assert target.is_active is False
    events = (
        await app_session.execute(
            select(AuditLog).where(
                AuditLog.table_name == "core_users", AuditLog.row_pk == target.id
            )
        )
    ).scalars().all()
    assert any((e.new_data or {}).get("event") == "user.deactivated" for e in events)


async def test_cannot_deactivate_self_or_break_glass(
    client, make_user, session_redis, seed_rbac
):
    admin, apw, secret = await _admin(make_user)
    bg, _ = await make_user(is_break_glass=True)
    await _login(client, admin, apw, secret)

    me = await client.post(
        f"/api/v1/users/{admin.id}/deactivate", headers=CSRF
    )
    assert me.status_code == 409  # cannot deactivate self

    glass = await client.post(
        f"/api/v1/users/{bg.id}/deactivate", headers=CSRF
    )
    assert glass.status_code == 409  # break-glass account is protected


async def test_reactivate(
    client, make_user, session_redis, seed_rbac, app_session
):
    admin, apw, secret = await _admin(make_user)
    target, _ = await make_user()
    await _login(client, admin, apw, secret)
    await client.post(f"/api/v1/users/{target.id}/deactivate", headers=CSRF)
    r = await client.post(f"/api/v1/users/{target.id}/reactivate", headers=CSRF)
    assert r.status_code == 200 and r.json()["is_active"] is True
