"""B3: auditor chain-verification report + per-record timeline (COA Res. 2020-034)."""

import pyotp

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


async def test_verify_report_renders_printable_html_pass(
    client, make_user, session_redis, seed_rbac
):
    auditor, pw = await make_user(roles=("auditor",))
    await _login(client, auditor, pw)
    r = await client.get("/api/v1/audit/verify")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "PASS" in r.text and "Audit Chain Verification Report" in r.text


async def test_verify_report_json_variant(client, make_user, session_redis, seed_rbac):
    auditor, pw = await make_user(roles=("auditor",))
    await _login(client, auditor, pw)
    r = await client.get(
        "/api/v1/audit/verify", headers={"Accept": "application/json"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "pass" and body["first_broken_row_id"] is None
    assert body["rows_checked"] >= 1


async def test_verify_denied_to_non_auditor(client, make_user, session_redis, seed_rbac):
    staff, pw = await make_user(roles=("staff",))
    await _login(client, staff, pw)
    r = await client.get("/api/v1/audit/verify")
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"


async def test_per_record_timeline(client, make_user, session_redis, seed_rbac):
    auditor, pw = await make_user(roles=("auditor",))
    await _login(client, auditor, pw)
    # The auditor's own core_users row was INSERTed — an auditable event.
    r = await client.get(f"/api/v1/audit/records/core_users/{auditor.id}")
    assert r.status_code == 200
    body = r.json()
    assert body["table_name"] == "core_users" and body["row_pk"] == auditor.id
    assert any(e["action"] == "insert" for e in body["entries"])


async def test_timeline_404_for_unknown_record(client, make_user, session_redis, seed_rbac):
    auditor, pw = await make_user(roles=("auditor",))
    await _login(client, auditor, pw)
    r = await client.get("/api/v1/audit/records/core_users/999999999")
    assert r.status_code == 404
