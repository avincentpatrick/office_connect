"""Redis-cached effective-permission set (Stage B / Increment 3, RBAC).

B2 shipped a MINIMAL, uncached ``require_permission`` — one 3-table join per
request. B3 puts that resolved permission set behind this cache so the hot
authorization path is a single Redis ``GET`` (no DB round-trip on a hit).

**Invalidation is version-keyed.** The cache key embeds
``core_users.permissions_version``; a grant/revoke bumps that column (and the
live session records, ``SessionStore.set_permissions_version``) so the very next
request builds a *different* key → cache miss → fresh DB load. The old entry is
never explicitly deleted — it is orphaned and TTL-collected. No pub/sub.

**Boundary-aware TTL.** A grant's ``valid_from``/``valid_to`` window changes the
effective set at a timestamp no version bump announces (a delegation simply
expires). So the loader also returns the next future window edge, and the entry's
TTL is capped at it — the cache drops precisely when the window opens/closes, and
the ``authz_cache_backstop_seconds`` setting is only the ceiling.

The Redis client is **injected** (never constructed here), exactly like
``SessionStore``, so ``core`` stays free of transport wiring and the
import-linter boundary holds.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from datetime import datetime

from redis.asyncio import Redis

from office_connect.core.config import Settings
from office_connect.core.time import utc_now

_PERM_PREFIX = "authz:perm:"

# The loader resolves the current effective set AND the next valid-window edge
# (or None if the user holds no time-bounded grant).
PermissionLoader = Callable[[], Awaitable[tuple[set[str], "datetime | None"]]]


class PermissionCache:
    def __init__(self, redis: Redis, settings: Settings) -> None:
        self._redis = redis
        self._settings = settings

    @staticmethod
    def _key(user_id: int, permissions_version: int) -> str:
        return f"{_PERM_PREFIX}{user_id}:v{permissions_version}"

    def _ttl_seconds(self, next_boundary: datetime | None, now: datetime) -> int:
        """Backstop, capped at the next valid-window edge (>= 1s)."""
        ttl = self._settings.authz_cache_backstop_seconds
        if next_boundary is not None:
            ttl = min(ttl, int((next_boundary - now).total_seconds()))
        return max(1, ttl)

    async def get_or_load(
        self,
        user_id: int,
        permissions_version: int,
        loader: PermissionLoader,
        *,
        now: datetime | None = None,
    ) -> set[str]:
        """Return the user's permission codes — from Redis on a hit, else via
        ``loader`` (the DB query), which is invoked ONLY on a miss so a cache hit
        never touches the database."""
        key = self._key(user_id, permissions_version)
        cached = await self._redis.get(key)
        if cached is not None:
            return set(json.loads(cached))
        codes, next_boundary = await loader()
        now = now or utc_now()
        await self._redis.set(
            key,
            json.dumps(sorted(codes)),
            ex=self._ttl_seconds(next_boundary, now),
        )
        return codes

    async def invalidate(self, user_id: int, permissions_version: int) -> None:
        """Drop a specific version's entry. Not required for correctness (the
        version bump already orphans it), but lets a grant/revoke reclaim the key
        immediately instead of waiting for the backstop."""
        await self._redis.delete(self._key(user_id, permissions_version))
