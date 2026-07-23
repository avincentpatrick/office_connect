"""B2: custom-header CSRF gate on non-safe methods (SameSite=Lax floor + header)."""


async def test_non_get_without_header_is_rejected(client):
    r = await client.post(
        "/api/v1/auth/login", json={"identifier": "a@doh.gov", "password": "x"}
    )
    assert r.status_code == 403 and r.json()["error"]["code"] == "csrf_failed"


async def test_non_get_with_header_passes_csrf(client, make_user, session_redis):
    user, pw = await make_user()
    r = await client.post(
        "/api/v1/auth/login",
        json={"identifier": user.email, "password": pw},
        headers={"X-Requested-With": "1"},
    )
    assert r.status_code != 403  # CSRF passed (authenticated)


async def test_get_is_exempt(client):
    assert (await client.get("/api/v1/config")).status_code == 200
