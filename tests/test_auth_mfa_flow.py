"""B2: MFA endpoints — enroll/confirm, two-step login, wrong code, enforcement."""

import pyotp
from sqlalchemy import select

from office_connect.core.models import User

CSRF = {"X-Requested-With": "1"}


async def test_enroll_then_confirm(client, make_user, session_redis, app_session):
    user, pw = await make_user()
    await client.post(
        "/api/v1/auth/login",
        json={"identifier": user.email, "password": pw},
        headers=CSRF,
    )
    enroll = await client.post("/api/v1/auth/mfa/enroll", headers=CSRF)
    assert enroll.status_code == 200
    secret = enroll.json()["secret"]
    assert enroll.json()["otpauth_uri"].startswith("otpauth://")

    await app_session.refresh(user)
    assert user.mfa_secret == secret and user.mfa_enabled is False

    confirm = await client.post(
        "/api/v1/auth/mfa/confirm",
        json={"code": pyotp.TOTP(secret).now()},
        headers=CSRF,
    )
    assert confirm.status_code == 200
    await app_session.refresh(user)
    assert user.mfa_enabled is True


async def test_login_two_step_mfa(client, make_user, session_redis):
    secret = pyotp.random_base32()
    user, pw = await make_user(mfa_enabled=True, mfa_secret=secret)
    login = await client.post(
        "/api/v1/auth/login",
        json={"identifier": user.email, "password": pw},
        headers=CSRF,
    )
    assert login.status_code == 200 and login.json()["status"] == "mfa_required"
    token = login.json()["mfa_token"]
    assert token and "set-cookie" not in {k.lower(): v for k, v in login.headers.items()}

    verify = await client.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_token": token, "code": pyotp.TOTP(secret).now()},
        headers=CSRF,
    )
    assert verify.status_code == 200 and verify.json()["status"] == "authenticated"


async def test_login_mfa_wrong_code(client, make_user, session_redis):
    secret = pyotp.random_base32()
    user, pw = await make_user(mfa_enabled=True, mfa_secret=secret)
    login = await client.post(
        "/api/v1/auth/login",
        json={"identifier": user.email, "password": pw},
        headers=CSRF,
    )
    token = login.json()["mfa_token"]
    verify = await client.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_token": token, "code": "000000"},
        headers=CSRF,
    )
    assert verify.status_code == 401 and verify.json()["error"]["code"] == "mfa_failed"


async def test_approver_without_mfa_is_forced_to_enroll(
    client, make_user, session_redis
):
    user, pw = await make_user(roles=("approver",))
    login = await client.post(
        "/api/v1/auth/login",
        json={"identifier": user.email, "password": pw},
        headers=CSRF,
    )
    assert login.status_code == 200 and login.json()["status"] == "mfa_setup_required"

    # A gated route is 403 until MFA is set up...
    gated = await client.get("/api/v1/auth/sessions")
    assert gated.status_code == 403 and gated.json()["error"]["code"] == "mfa_setup_required"
    # ...but enroll itself is reachable.
    enroll = await client.post("/api/v1/auth/mfa/enroll", headers=CSRF)
    assert enroll.status_code == 200
