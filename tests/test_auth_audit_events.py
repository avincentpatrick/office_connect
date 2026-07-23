"""B2: auth events ride the hash chain; secrets stay redacted; actor is real."""

import pytest
from sqlalchemy import select

from office_connect.core.audit import append_auth_event, verify_chain
from office_connect.core.models import AuditLog

CSRF = {"X-Requested-With": "1"}


async def _login(client, user, pw):
    return await client.post(
        "/api/v1/auth/login",
        json={"identifier": user.email, "password": pw},
        headers=CSRF,
    )


async def test_logout_writes_a_chain_row_without_secrets(
    client, make_user, session_redis, app_session
):
    user, pw = await make_user()
    await _login(client, user, pw)
    await client.post("/api/v1/auth/logout", headers=CSRF)

    rows = (
        await app_session.execute(
            select(AuditLog).where(
                AuditLog.table_name == "core_sessions", AuditLog.row_pk == user.id
            )
        )
    ).scalars().all()
    logout = [r for r in rows if (r.new_data or {}).get("event") == "auth.logout"]
    assert logout
    row = logout[-1]
    assert row.action == "insert" and row.actor_id == user.id
    assert "password" not in row.new_data and "session_id" not in row.new_data


async def test_chain_stays_intact_through_events(
    client, make_user, session_redis, owner_session
):
    user, pw = await make_user()
    await _login(client, user, pw)
    await client.post("/api/v1/auth/logout", headers=CSRF)
    rows = (
        await owner_session.execute(select(AuditLog).order_by(AuditLog.id))
    ).scalars().all()
    assert verify_chain(rows) is None


async def test_password_change_redacts_the_hash(
    client, make_user, session_redis, app_session
):
    user, pw = await make_user()
    await _login(client, user, pw)
    await client.post(
        "/api/v1/auth/password/change",
        json={"current_password": pw, "new_password": "a-fresh-unblocked-passphrase-2026"},
        headers=CSRF,
    )
    rows = (
        await app_session.execute(
            select(AuditLog).where(
                AuditLog.table_name == "core_users",
                AuditLog.row_pk == user.id,
                AuditLog.action == "update",
            ).order_by(AuditLog.id)
        )
    ).scalars().all()
    assert rows and rows[-1].new_data.get("password_hash") == "[redacted]"


async def test_authenticated_write_attributes_real_actor(
    client, make_user, session_redis, app_session
):
    """Login stamps last_login_at (a core_users UPDATE) with actor_id = the user."""
    user, pw = await make_user()
    await _login(client, user, pw)
    row = (
        await app_session.execute(
            select(AuditLog).where(
                AuditLog.table_name == "core_users",
                AuditLog.row_pk == user.id,
                AuditLog.action == "update",
            ).order_by(AuditLog.id.desc())
        )
    ).scalars().first()
    assert row is not None and row.actor_id == user.id


async def test_append_auth_event_rejects_a_secret_key(app_session, make_user):
    user, _pw = await make_user()
    with pytest.raises(ValueError):
        await append_auth_event(
            app_session, event="auth.logout", subject_user_id=user.id,
            data={"password": "leak"},
        )
