"""Throttle-not-lockout (auth-rbac-onprem.md).

Per-account AND per-IP Redis counters with **exponential backoff** after N=5
consecutive failures — never a permanent lock (NIST 800-63B permits throttling,
not lockout). The counter resets on success. Both counters increment even for an
**unknown identifier**, so a 429 never reveals whether an account exists. The
account identifier is hashed into the key, so raw emails never sit in the keyspace.

Mechanics: each failure ``INCR``s a sliding-window counter; once it reaches the
threshold, a short-lived ``:until`` key is set with TTL = the backoff delay.
``check`` returns blocked while any ``:until`` key has time left (its TTL is the
``Retry-After``). Waiting out the delay unblocks — it is a delay, not a lock.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from redis.asyncio import Redis

from office_connect.core.config import Settings

_ACCT_PREFIX = "throttle:acct:"
_IP_PREFIX = "throttle:ip:"


@dataclass(frozen=True, slots=True)
class ThrottleDecision:
    allowed: bool
    retry_after: int  # seconds until the caller may try again (0 when allowed)


def _acct_key(identifier: str) -> str:
    digest = hashlib.sha256(identifier.strip().casefold().encode("utf-8")).hexdigest()
    return f"{_ACCT_PREFIX}{digest}"


def _ip_key(ip: str) -> str:
    return f"{_IP_PREFIX}{ip}"


class LoginThrottle:
    def __init__(self, redis: Redis, settings: Settings) -> None:
        self._redis = redis
        self._threshold = settings.throttle_threshold
        self._base = settings.throttle_backoff_base_seconds
        self._ceiling = settings.throttle_backoff_ceiling_seconds
        self._window = settings.throttle_window_seconds

    def _backoff_seconds(self, fails: int) -> int:
        if fails < self._threshold:
            return 0
        return min(self._base * (2 ** (fails - self._threshold)), self._ceiling)

    def _keys(self, identifier: str, ip: str | None) -> list[str]:
        keys = [_acct_key(identifier)]
        if ip:
            keys.append(_ip_key(ip))
        return keys

    async def check(self, identifier: str, ip: str | None) -> ThrottleDecision:
        pipe = self._redis.pipeline()
        for key in self._keys(identifier, ip):
            pipe.pttl(f"{key}:until")
        ttls = await pipe.execute()
        retry = 0
        for pttl in ttls:
            if pttl and pttl > 0:
                retry = max(retry, (pttl + 999) // 1000)  # ceil ms -> s
        return ThrottleDecision(allowed=(retry == 0), retry_after=retry)

    async def register_failure(self, identifier: str, ip: str | None) -> None:
        for key in self._keys(identifier, ip):
            fails = await self._redis.incr(key)
            await self._redis.expire(key, self._window)
            delay = self._backoff_seconds(fails)
            if delay > 0:
                await self._redis.set(f"{key}:until", "1", ex=delay)

    async def reset(self, identifier: str, ip: str | None) -> None:
        pipe = self._redis.pipeline()
        for key in self._keys(identifier, ip):
            pipe.delete(key)
            pipe.delete(f"{key}:until")
        await pipe.execute()
