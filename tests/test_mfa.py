"""B2: TOTP MFA — codes, skew window, fail-closed, single-use replay guard."""

from datetime import timedelta

import pyotp

from office_connect.core.auth import mfa
from office_connect.core.time import utc_now


def test_generate_secret_is_base32():
    secret = mfa.generate_secret()
    assert len(secret) >= 16 and secret.isalnum()


def test_provisioning_uri_carries_issuer_and_secret():
    secret = mfa.generate_secret()
    uri = mfa.provisioning_uri(secret, "a@doh.gov", "Office-Connect")
    assert uri.startswith("otpauth://totp/")
    assert "issuer=Office-Connect" in uri
    assert secret in uri


def test_verify_current_accepts_and_wrong_rejects():
    secret = mfa.generate_secret()
    assert mfa.verify_code(secret, pyotp.TOTP(secret).now())
    assert not mfa.verify_code(secret, "000000")


def test_skew_window():
    secret = mfa.generate_secret()
    now = utc_now()
    one_back = pyotp.TOTP(secret).at(now - timedelta(seconds=30))
    assert mfa.verify_code(secret, one_back, valid_window=1, at_time=now)
    three_back = pyotp.TOTP(secret).at(now - timedelta(seconds=90))
    assert not mfa.verify_code(secret, three_back, valid_window=1, at_time=now)


def test_fail_closed_on_garbage():
    assert not mfa.verify_code("", "123456")
    assert not mfa.verify_code(mfa.generate_secret(), "")
    assert not mfa.verify_code("not-valid-base32!!", "123456")


async def test_check_and_consume_rejects_replay(session_redis):
    secret = mfa.generate_secret()
    code = pyotp.TOTP(secret).now()
    assert await mfa.check_and_consume(session_redis, 123, secret, code)
    assert not await mfa.check_and_consume(session_redis, 123, secret, code)
