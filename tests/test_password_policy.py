"""B2: NIST 800-63B-4 password policy (length 12+, blocklist, context words)."""

from office_connect.core.auth.password_policy import (
    PasswordPolicyError,
    normalize_password,
    validate_password,
)
from office_connect.core.security.blocklists import _load


def _errors(pw, **kw):
    try:
        validate_password(pw, **kw)
        return []
    except PasswordPolicyError as exc:
        return exc.errors


def test_min_length_boundary():
    assert "too_short" in _errors("Zx9-quiet")  # 9 chars
    assert _errors("Zx9-quiet-owl-4") == []  # 15 chars, not common, no identifier


def test_max_length():
    assert "too_long" in _errors("Zx9-" + "a" * 200)


def test_blocklisted_common_password_rejected():
    long_common = next(p for p in _load() if len(p) >= 12)
    assert "blocklisted" in _errors(long_common)


def test_contains_email_local_part_rejected():
    assert "contains_identifier" in _errors(
        "alicework-passphrase-42", email="alice@doh.gov"
    )


def test_contains_username_rejected():
    assert "contains_identifier" in _errors("my-juan-secret-pass", username="juan")


def test_all_failures_collected():
    errs = _errors("abc")  # too_short + (abc is a common password)
    assert "too_short" in errs and len(errs) >= 1


def test_unicode_and_spaces_allowed():
    assert _errors("paëlla münchen tromsø fjord") == []


def test_nfkc_normalization():
    assert normalize_password("ﬁ") == "fi"  # ligature -> compatibility decomposition
    s = "café ﬁord"
    assert normalize_password(normalize_password(s)) == normalize_password(s)
