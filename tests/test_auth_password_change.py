"""B2: password change — must-change gate, revoke-others, policy, reauth."""

CSRF = {"X-Requested-With": "1"}
NEW_PW = "a-fresh-unblocked-passphrase-2026"


async def test_must_change_gates_then_clears(client, make_user, session_redis):
    user, pw = await make_user(must_change_password=True)
    login = await client.post(
        "/api/v1/auth/login",
        json={"identifier": user.email, "password": pw},
        headers=CSRF,
    )
    assert login.json()["status"] == "password_change_required"

    gated = await client.get("/api/v1/auth/sessions")
    assert gated.status_code == 403
    assert gated.json()["error"]["code"] == "password_change_required"

    changed = await client.post(
        "/api/v1/auth/password/change",
        json={"current_password": pw, "new_password": NEW_PW},
        headers=CSRF,
    )
    assert changed.status_code == 200
    assert (await client.get("/api/v1/auth/sessions")).status_code == 200


async def test_change_revokes_other_sessions(
    client, make_user, session_redis, session_store
):
    user, pw = await make_user()
    await client.post(
        "/api/v1/auth/login",
        json={"identifier": user.email, "password": pw},
        headers=CSRF,
    )
    other, _ = await session_store.create_session(
        user_id=user.id, email=user.email, permissions_version=0,
        roles=[], ip=None, user_agent=None,
    )
    changed = await client.post(
        "/api/v1/auth/password/change",
        json={"current_password": pw, "new_password": NEW_PW},
        headers=CSRF,
    )
    assert changed.status_code == 200
    assert await session_store.get_session_record(other) is None


async def test_change_rejects_weak_password(client, make_user, session_redis):
    user, pw = await make_user()
    await client.post(
        "/api/v1/auth/login",
        json={"identifier": user.email, "password": pw},
        headers=CSRF,
    )
    r = await client.post(
        "/api/v1/auth/password/change",
        json={"current_password": pw, "new_password": "short"},
        headers=CSRF,
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "password_policy"
    assert "too_short" in r.json()["error"]["details"]


async def test_change_rejects_wrong_current(client, make_user, session_redis):
    user, pw = await make_user()
    await client.post(
        "/api/v1/auth/login",
        json={"identifier": user.email, "password": pw},
        headers=CSRF,
    )
    r = await client.post(
        "/api/v1/auth/password/change",
        json={"current_password": "not-the-current-pw", "new_password": NEW_PW},
        headers=CSRF,
    )
    assert r.status_code == 401
