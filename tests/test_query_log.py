"""Stage B (Phase 2) Increment 4 — query-log access middleware.

One append-only ``core_query_logs`` row per ``/api/v1`` request (reads + writes,
authed + anonymous), excluding ``/config``; ids/param-NAMES/status only — never
bodies, headers, or query VALUES. A logging failure never breaks the request.
Tests correlate rows by a caller-supplied ``X-Request-ID``.
"""

import json
import uuid

from sqlalchemy import select

from office_connect.core.models import QueryLog

CSRF = {"X-Requested-With": "1"}


async def _login(client, user, pw):
    return await client.post(
        "/api/v1/auth/login",
        json={"identifier": user.email, "password": pw},
        headers=CSRF,
    )


async def _rows_for(session, rid):
    return (
        (await session.execute(select(QueryLog).where(QueryLog.request_id == rid)))
        .scalars()
        .all()
    )


async def test_config_request_not_logged(client, app_session):
    rid = uuid.uuid4().hex
    r = await client.get("/api/v1/config", headers={"X-Request-ID": rid})
    assert r.status_code == 200
    assert await _rows_for(app_session, rid) == []  # excluded path


async def test_authenticated_request_logged(
    client, make_user, session_redis, app_session
):
    user, pw = await make_user()
    await _login(client, user, pw)
    rid = uuid.uuid4().hex
    r = await client.get("/api/v1/auth/me", headers={"X-Request-ID": rid})
    assert r.status_code == 200

    rows = await _rows_for(app_session, rid)
    assert len(rows) == 1
    row = rows[0]
    assert row.module == "auth" and row.resource == "me" and row.action == "read"
    assert row.created_by == user.id
    assert row.detail["status_code"] == 200
    assert set(row.detail.keys()) == {
        "method",
        "path",
        "path_params",
        "query_keys",
        "status_code",
        "duration_ms",
    }


async def test_anonymous_request_logged_with_null_actor(client, app_session):
    rid = uuid.uuid4().hex
    r = await client.get("/api/v1/rbac/roles", headers={"X-Request-ID": rid})
    assert r.status_code == 401  # protected → anonymous denied, but still logged
    rows = await _rows_for(app_session, rid)
    assert len(rows) == 1
    assert rows[0].created_by is None
    assert rows[0].detail["status_code"] == 401


async def test_query_values_never_logged(
    client, make_user, session_redis, app_session
):
    user, pw = await make_user()
    await _login(client, user, pw)
    rid = uuid.uuid4().hex
    await client.get("/api/v1/auth/me?q=topsecret", headers={"X-Request-ID": rid})
    rows = await _rows_for(app_session, rid)
    assert len(rows) == 1
    assert rows[0].detail["query_keys"] == ["q"]  # NAME kept
    assert "topsecret" not in json.dumps(rows[0].detail)  # VALUE never stored


async def test_log_failure_does_not_break_request(
    client, make_user, session_redis, monkeypatch
):
    user, pw = await make_user()
    await _login(client, user, pw)

    from office_connect.core.api import query_log_middleware as qlm

    def _boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(qlm, "SessionLocal", _boom)
    r = await client.get("/api/v1/auth/me")
    assert r.status_code == 200  # the swallowed log error never surfaces
