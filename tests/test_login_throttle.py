"""B2: throttle-not-lockout — backoff, reset-on-success, per-IP/per-account."""

from office_connect.core.auth.throttle import LoginThrottle
from office_connect.core.config import get_settings


def test_backoff_monotonic_and_capped():
    t = LoginThrottle(None, get_settings())  # _backoff_seconds is pure, no Redis
    assert [t._backoff_seconds(i) for i in range(5)] == [0, 0, 0, 0, 0]
    seq = [t._backoff_seconds(i) for i in range(5, 12)]
    assert seq == sorted(seq) and seq[0] == 1
    assert t._backoff_seconds(1000) == get_settings().throttle_backoff_ceiling_seconds


async def test_blocks_after_threshold(session_redis):
    t = LoginThrottle(session_redis, get_settings())
    assert (await t.check("carol@x", "2.2.2.2")).allowed
    for _ in range(5):
        await t.register_failure("carol@x", "2.2.2.2")
    d = await t.check("carol@x", "2.2.2.2")
    assert not d.allowed and d.retry_after > 0


async def test_reset_on_success(session_redis):
    t = LoginThrottle(session_redis, get_settings())
    for _ in range(5):
        await t.register_failure("bob@x", "1.1.1.1")
    assert not (await t.check("bob@x", "1.1.1.1")).allowed
    await t.reset("bob@x", "1.1.1.1")
    assert (await t.check("bob@x", "1.1.1.1")).allowed


async def test_per_ip_blocks_a_different_identifier(session_redis):
    """Enumeration parity: the per-IP counter blocks even an unknown identifier."""
    t = LoginThrottle(session_redis, get_settings())
    for _ in range(6):
        await t.register_failure("real@x", "3.3.3.3")
    assert not (await t.check("ghost@x", "3.3.3.3")).allowed


async def test_per_account_increments_for_unknown_identifier(session_redis):
    t = LoginThrottle(session_redis, get_settings())
    for _ in range(5):
        await t.register_failure("ghost-acct@x", None)
    assert not (await t.check("ghost-acct@x", None)).allowed
