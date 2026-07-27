"""B3: RBAC enforcement end-to-end — cache-backed gate, grant/revoke land on the
next request, admin API bumps version + emits events, auditor is read-only."""

import pyotp
from sqlalchemy import select

from office_connect.core.models import AuditLog, Role, User
from office_connect.core.rbac import grant_role, revoke_role

CSRF = {"X-Requested-With": "1"}


async def _login(client, user, pw, mfa_secret=None):
    r = await client.post(
        "/api/v1/auth/login",
        json={"identifier": user.email, "password": pw},
        headers=CSRF,
    )
    if r.json().get("status") == "mfa_required":
        r = await client.post(
            "/api/v1/auth/mfa/verify",
            json={"mfa_token": r.json()["mfa_token"], "code": pyotp.TOTP(mfa_secret).now()},
            headers=CSRF,
        )
    return r


async def _role_id(session, code):
    return (
        await session.execute(select(Role).where(Role.code == code))
    ).scalar_one().id


async def test_denied_without_the_permission(client, make_user, session_redis, seed_rbac):
    user, pw = await make_user(roles=("staff",))
    await _login(client, user, pw)
    r = await client.get("/api/v1/rbac/roles")  # requires rbac.role.read
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"


async def test_grant_lands_on_next_request(
    client, make_user, session_redis, session_store, permission_cache, app_session, seed_rbac
):
    target, pw = await make_user(roles=("staff",))
    admin, _ = await make_user(roles=("system_admin",))
    await _login(client, target, pw)
    # Before: staff has no rbac.role.read.
    assert (await client.get("/api/v1/rbac/roles")).status_code == 403
    # Grant auditor (carries rbac.role.read, not an MFA-required role).
    await grant_role(
        app_session,
        session_store,
        permission_cache,
        target_user_id=target.id,
        role_id=await _role_id(app_session, "auditor"),
        actor_id=admin.id,
    )
    # After: the SAME session authorizes — the version bump landed this request.
    assert (await client.get("/api/v1/rbac/roles")).status_code == 200


async def test_revoke_lands_on_next_request(
    client, make_user, session_redis, session_store, permission_cache, app_session, seed_rbac
):
    target, pw = await make_user(roles=("staff",))
    admin, _ = await make_user(roles=("system_admin",))
    grant = await grant_role(
        app_session,
        session_store,
        permission_cache,
        target_user_id=target.id,
        role_id=await _role_id(app_session, "auditor"),
        actor_id=admin.id,
    )
    await _login(client, target, pw)
    assert (await client.get("/api/v1/rbac/roles")).status_code == 200
    await revoke_role(
        app_session,
        session_store,
        permission_cache,
        target_user_id=target.id,
        grant_id=grant.id,
        actor_id=admin.id,
    )
    assert (await client.get("/api/v1/rbac/roles")).status_code == 403


async def test_admin_grants_via_http_bumps_version_and_audits(
    client, make_user, session_redis, app_session, seed_rbac
):
    secret = pyotp.random_base32()
    admin, pw = await make_user(
        roles=("system_admin",), mfa_enabled=True, mfa_secret=secret
    )
    target, _ = await make_user(roles=("staff",))
    login = await _login(client, admin, pw, secret)
    assert login.status_code == 200 and login.json()["status"] == "authenticated"

    auditor_id = await _role_id(app_session, "auditor")
    resp = await client.post(
        f"/api/v1/rbac/users/{target.id}/roles",
        json={"role_id": auditor_id},
        headers=CSRF,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] == target.id and body["role_id"] == auditor_id

    await app_session.refresh(target)
    assert target.permissions_version == 1  # bumped by the grant

    events = (
        await app_session.execute(
            select(AuditLog).where(
                AuditLog.table_name == "core_user_roles",
                AuditLog.row_pk == body["id"],
            )
        )
    ).scalars().all()
    assert any((e.new_data or {}).get("event") == "rbac.role.granted" for e in events)


async def test_auditor_is_read_only_everywhere(
    client, make_user, session_redis, seed_rbac
):
    auditor, pw = await make_user(roles=("auditor",))
    target, _ = await make_user(roles=("staff",))
    await _login(client, auditor, pw)
    # Allowed: the read-only chain-verification report.
    assert (await client.get("/api/v1/audit/verify")).status_code == 200
    # Denied: any write — auditor holds no grant permission.
    r = await client.post(
        f"/api/v1/rbac/users/{target.id}/roles",
        json={"role_id": 1},
        headers=CSRF,
    )
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"
