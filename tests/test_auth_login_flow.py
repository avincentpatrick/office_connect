"""B2: login endpoint — cookie, anti-enumeration, throttle, break-glass, rehash."""

from sqlalchemy import select

from office_connect.core.models import LoginAttempt, User

CSRF = {"X-Requested-With": "1"}


async def test_login_sets_cookie_and_logs_success(
    client, make_user, session_redis, app_session
):
    user, pw = await make_user()
    r = await client.post(
        "/api/v1/auth/login",
        json={"identifier": user.email, "password": pw},
        headers=CSRF,
    )
    assert r.status_code == 200 and r.json()["status"] == "authenticated"
    set_cookie = r.headers.get("set-cookie", "").lower()
    assert "oc_session=" in set_cookie
    assert "httponly" in set_cookie and "samesite=lax" in set_cookie

    row = (
        await app_session.execute(
            select(LoginAttempt)
            .where(LoginAttempt.user_id == user.id)
            .order_by(LoginAttempt.id.desc())
        )
    ).scalars().first()
    assert row.outcome == "success" and row.session_id_hash and row.failure_reason is None


async def test_unknown_user_and_wrong_password_indistinguishable(
    client, make_user, session_redis
):
    user, _pw = await make_user()
    r1 = await client.post(
        "/api/v1/auth/login",
        json={"identifier": user.email, "password": "definitely-wrong-1"},
        headers=CSRF,
    )
    r2 = await client.post(
        "/api/v1/auth/login",
        json={"identifier": "ghost@doh.gov", "password": "definitely-wrong-1"},
        headers=CSRF,
    )
    assert r1.status_code == r2.status_code == 401
    assert r1.json()["error"]["code"] == r2.json()["error"]["code"] == "invalid_credentials"
    assert r1.json()["error"]["message"] == r2.json()["error"]["message"]


async def test_inactive_user_gets_generic_401(
    client, make_user, session_redis, app_session
):
    user, pw = await make_user()
    user.is_active = False
    app_session.add(user)
    await app_session.commit()
    r = await client.post(
        "/api/v1/auth/login",
        json={"identifier": user.email, "password": pw},
        headers=CSRF,
    )
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_credentials"


async def test_throttle_after_five_failures(client, make_user, session_redis):
    user, pw = await make_user()
    for _ in range(5):
        await client.post(
            "/api/v1/auth/login",
            json={"identifier": user.email, "password": "wrong-wrong-wrong"},
            headers=CSRF,
        )
    r = await client.post(
        "/api/v1/auth/login",
        json={"identifier": user.email, "password": pw},
        headers=CSRF,
    )
    assert r.status_code == 429 and r.json()["error"]["code"] == "too_many_attempts"
    assert any(k.lower() == "retry-after" for k in r.headers)


async def test_break_glass_logs_in_locally(client, make_user, session_redis):
    user, pw = await make_user(is_break_glass=True)
    r = await client.post(
        "/api/v1/auth/login",
        json={"identifier": user.email, "password": pw},
        headers=CSRF,
    )
    assert r.status_code == 200 and r.json()["status"] == "authenticated"


async def test_needs_rehash_upgrades_transparently(
    client, make_user, session_redis, app_session
):
    import argon2

    weak = argon2.PasswordHasher(time_cost=1, memory_cost=19 * 1024, parallelism=1).hash(
        "correct-horse-battery-staple"
    )
    user, _ = await make_user(password=None)
    user.password_hash = weak
    app_session.add(user)
    await app_session.commit()

    r = await client.post(
        "/api/v1/auth/login",
        json={"identifier": user.email, "password": "correct-horse-battery-staple"},
        headers=CSRF,
    )
    assert r.status_code == 200
    await app_session.refresh(user)
    assert user.password_hash != weak  # re-hashed to the current cost params
