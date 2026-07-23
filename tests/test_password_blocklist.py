"""B2: the vendored top-100k blocklist loads and matches (normalized)."""

from office_connect.core.security.blocklists import (
    _load,
    blocklist_size,
    is_blocklisted,
)


def test_loads_nonempty():
    assert blocklist_size() > 50_000


def test_known_common_passwords_blocked():
    assert is_blocklisted("password")
    assert is_blocklisted("123456")
    assert is_blocklisted("qwerty")


def test_random_passphrase_not_blocked():
    assert not is_blocklisted("Zq7-vermillion-abacus-lantern-93")


def test_casefold_and_strip_normalization():
    assert is_blocklisted("PASSWORD")
    assert is_blocklisted("  password  ")


def test_load_is_cached():
    assert _load() is _load()
