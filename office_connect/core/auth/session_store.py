"""Redis server-side session store (auth-rbac-onprem.md).

The opaque session id (``secrets.token_urlsafe(32)``, 256-bit) lives in an
HttpOnly cookie; the server-side record lives in a Redis **Hash** ``session:{sid}``
on a dedicated logical DB (db 4). A per-user **sorted set** ``user_sessions:{uid}``
(score = created_at) indexes a user's live sessions for revoke-all + the
concurrent-session cap + ordered "active sessions" listing.

Design choices:
- **Hash, not a JSON string**, so ``touch`` writes only ``last_seen_at`` (a
  field-level ``HSET``) and can't clobber immutable fields raced against a rotate.
- **Sorted set** (score = created_at) gives O(log n) oldest-eviction, ordered
  listing, and cheap ``ZCARD`` for the cap.
- **Absolute vs idle TTL**: the Redis key TTL is set to
  ``max(1, min(idle_seconds, absolute_remaining))`` on create and every touch, so
  a continuously-active session still can't outlive its absolute cap; the in-app
  ``policy.expiry_reason`` check (on every read) is authoritative.
- **Lazy index reconciliation**: Redis EXPIRE drops the ``session:{sid}`` hash but
  not its sorted-set member, so read paths prune members whose hash no longer
  exists (``_prune_user_index``); the set itself carries an absolute-lifetime TTL
  so a dormant user's index self-collects.

The raw sid never leaves the server: APIs address a session by
``sha256(sid)`` (the same value stored in ``core_login_attempts.session_id_hash``).
The Redis client is **injected** (never constructed here) so ``core`` stays free
of transport wiring and the import-linter boundary holds.
"""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

from redis.asyncio import Redis

from office_connect.core.auth import policy
from office_connect.core.config import Settings
from office_connect.core.time import UTC, utc_now

_SESSION_PREFIX = "session:"
_USER_PREFIX = "user_sessions:"


class SessionCapReached(Exception):
    """Raised by ``create_session`` when the cap policy is "reject" and full."""


def _ts(value: str) -> datetime:
    return datetime.fromtimestamp(float(value), tz=UTC)


@dataclass(frozen=True, slots=True)
class SessionRecord:
    sid: str
    user_id: int
    email: str
    permissions_version: int
    created_at: datetime
    last_seen_at: datetime
    last_auth_at: datetime
    ip: str | None
    user_agent: str | None
    idle_tier: str
    roles: tuple[str, ...]
    must_change_password: bool
    mfa_setup_required: bool
    mfa_authenticated: bool

    @property
    def is_privileged(self) -> bool:
        return self.idle_tier == "privileged"

    @property
    def session_id_hash(self) -> str:
        return hashlib.sha256(self.sid.encode("utf-8")).hexdigest()


class SessionStore:
    def __init__(self, redis: Redis, settings: Settings) -> None:
        self._redis = redis
        self._settings = settings

    # --- key helpers ------------------------------------------------------
    @staticmethod
    def _skey(sid: str) -> str:
        return f"{_SESSION_PREFIX}{sid}"

    @staticmethod
    def _ukey(user_id: int) -> str:
        return f"{_USER_PREFIX}{user_id}"

    # --- (de)serialization ------------------------------------------------
    @staticmethod
    def _encode(rec: SessionRecord) -> dict[str, str]:
        return {
            "user_id": str(rec.user_id),
            "email": rec.email or "",
            "permissions_version": str(rec.permissions_version),
            "created_at": str(rec.created_at.timestamp()),
            "last_seen_at": str(rec.last_seen_at.timestamp()),
            "last_auth_at": str(rec.last_auth_at.timestamp()),
            "ip": rec.ip or "",
            "user_agent": rec.user_agent or "",
            "idle_tier": rec.idle_tier,
            "roles": ",".join(rec.roles),
            "must_change_password": "1" if rec.must_change_password else "0",
            "mfa_setup_required": "1" if rec.mfa_setup_required else "0",
            "mfa_authenticated": "1" if rec.mfa_authenticated else "0",
        }

    @staticmethod
    def _decode(sid: str, m: dict[str, str]) -> SessionRecord:
        return SessionRecord(
            sid=sid,
            user_id=int(m["user_id"]),
            email=m.get("email") or "",
            permissions_version=int(m.get("permissions_version") or "0"),
            created_at=_ts(m["created_at"]),
            last_seen_at=_ts(m["last_seen_at"]),
            last_auth_at=_ts(m.get("last_auth_at") or m["created_at"]),
            ip=m.get("ip") or None,
            user_agent=m.get("user_agent") or None,
            idle_tier=m.get("idle_tier") or "staff",
            roles=tuple(r for r in (m.get("roles") or "").split(",") if r),
            must_change_password=m.get("must_change_password") == "1",
            mfa_setup_required=m.get("mfa_setup_required") == "1",
            mfa_authenticated=m.get("mfa_authenticated") == "1",
        )

    def _ttl_seconds(self, rec: SessionRecord, now: datetime) -> int:
        idle = policy.idle_seconds_for(rec.idle_tier, self._settings)
        absolute_remaining = int(
            (
                policy.absolute_expires_at(rec.created_at, self._settings) - now
            ).total_seconds()
        )
        return max(1, min(idle, absolute_remaining))

    # --- public API -------------------------------------------------------
    async def create_session(
        self,
        *,
        user_id: int,
        email: str,
        permissions_version: int,
        roles: Sequence[str],
        ip: str | None,
        user_agent: str | None,
        must_change_password: bool = False,
        mfa_setup_required: bool = False,
        mfa_authenticated: bool = True,
        now: datetime | None = None,
    ) -> tuple[str, SessionRecord]:
        """Mint a fresh session (session-fixation defense: a brand-new id, never
        reused from before login). Enforces the concurrent-session cap first."""
        now = now or utc_now()
        await self._enforce_cap(user_id, now=now)
        sid = secrets.token_urlsafe(32)
        roles = tuple(roles)
        rec = SessionRecord(
            sid=sid,
            user_id=user_id,
            email=email,
            permissions_version=permissions_version,
            created_at=now,
            last_seen_at=now,
            last_auth_at=now,
            ip=ip,
            user_agent=user_agent,
            idle_tier=policy.idle_tier_for(roles),
            roles=roles,
            must_change_password=must_change_password,
            mfa_setup_required=mfa_setup_required,
            mfa_authenticated=mfa_authenticated,
        )
        skey, ukey = self._skey(sid), self._ukey(user_id)
        pipe = self._redis.pipeline()
        pipe.hset(skey, mapping=self._encode(rec))
        pipe.expire(skey, self._ttl_seconds(rec, now))
        pipe.zadd(ukey, {sid: now.timestamp()})
        pipe.expire(ukey, self._settings.session_absolute_seconds)
        await pipe.execute()
        return sid, rec

    async def get_session_record(
        self, sid: str, *, now: datetime | None = None
    ) -> SessionRecord | None:
        """Load a session, enforcing absolute/idle expiry (self-destructs if expired)."""
        now = now or utc_now()
        mapping = await self._redis.hgetall(self._skey(sid))
        if not mapping:
            return None
        rec = self._decode(sid, mapping)
        if policy.expiry_reason(
            created_at=rec.created_at,
            last_seen_at=rec.last_seen_at,
            idle_tier=rec.idle_tier,
            settings=self._settings,
            now=now,
        ):
            await self.destroy(sid, user_id=rec.user_id)
            return None
        return rec

    async def touch(
        self, sid: str, *, now: datetime | None = None
    ) -> SessionRecord | None:
        """Slide ``last_seen_at`` and re-cap the TTL. None if now-expired."""
        now = now or utc_now()
        rec = await self.get_session_record(sid, now=now)
        if rec is None:
            return None
        rec = replace(rec, last_seen_at=now)
        skey = self._skey(sid)
        pipe = self._redis.pipeline()
        pipe.hset(skey, "last_seen_at", str(now.timestamp()))
        pipe.expire(skey, self._ttl_seconds(rec, now))
        await pipe.execute()
        return rec

    async def regenerate_id(
        self, sid: str, *, now: datetime | None = None, **overrides: Any
    ) -> tuple[str, SessionRecord] | None:
        """Rotate the session id (anti-fixation) keeping the same lifetime.

        ``overrides`` mutate record fields atomically with the rotation — e.g.
        ``mfa_authenticated=True`` + ``last_auth_at=now`` on MFA completion, or
        a bumped ``permissions_version`` on privilege change. Copy→delete runs in
        a single MULTI/EXEC so the old and new ids never both vanish.
        """
        now = now or utc_now()
        rec = await self.get_session_record(sid, now=now)
        if rec is None:
            return None
        new_sid = secrets.token_urlsafe(32)
        if "roles" in overrides:
            roles = tuple(overrides["roles"])
            overrides["roles"] = roles
            overrides.setdefault("idle_tier", policy.idle_tier_for(roles))
        new_rec = replace(rec, sid=new_sid, **overrides)
        old_skey, new_skey = self._skey(sid), self._skey(new_sid)
        ukey = self._ukey(rec.user_id)
        pipe = self._redis.pipeline(transaction=True)
        pipe.hset(new_skey, mapping=self._encode(new_rec))
        pipe.expire(new_skey, self._ttl_seconds(new_rec, now))
        pipe.zadd(ukey, {new_sid: new_rec.created_at.timestamp()})
        pipe.zrem(ukey, sid)
        pipe.delete(old_skey)
        await pipe.execute()
        return new_sid, new_rec

    async def destroy(self, sid: str, *, user_id: int | None = None) -> None:
        """Delete the server-side record (deleting the cookie alone is not logout)."""
        if user_id is None:
            raw = await self._redis.hget(self._skey(sid), "user_id")
            user_id = int(raw) if raw is not None else None
        pipe = self._redis.pipeline()
        pipe.delete(self._skey(sid))
        if user_id is not None:
            pipe.zrem(self._ukey(user_id), sid)
        await pipe.execute()

    async def destroy_all_for_user(
        self, user_id: int, *, except_sid: str | None = None
    ) -> int:
        """Revoke every session for a user (password change / deactivation)."""
        ukey = self._ukey(user_id)
        sids = await self._redis.zrange(ukey, 0, -1)
        pipe = self._redis.pipeline()
        count = 0
        for sid in sids:
            if except_sid is not None and sid == except_sid:
                continue
            pipe.delete(self._skey(sid))
            pipe.zrem(ukey, sid)
            count += 1
        if count:
            await pipe.execute()
        return count

    async def list_for_user(
        self, user_id: int, *, now: datetime | None = None
    ) -> list[SessionRecord]:
        now = now or utc_now()
        await self._prune_user_index(user_id)
        sids = await self._redis.zrange(self._ukey(user_id), 0, -1)
        out: list[SessionRecord] = []
        for sid in sids:
            rec = await self.get_session_record(sid, now=now)
            if rec is not None:
                out.append(rec)
        return out

    async def resolve_handle(self, user_id: int, session_id_hash: str) -> str | None:
        """Map a public ``sha256(sid)`` handle back to the raw sid, but only within
        this user's own index — so a caller can never address someone else's session."""
        await self._prune_user_index(user_id)
        sids = await self._redis.zrange(self._ukey(user_id), 0, -1)
        for sid in sids:
            if hashlib.sha256(sid.encode("utf-8")).hexdigest() == session_id_hash:
                return sid
        return None

    # --- internals --------------------------------------------------------
    async def _prune_user_index(self, user_id: int) -> None:
        ukey = self._ukey(user_id)
        sids = await self._redis.zrange(ukey, 0, -1)
        if not sids:
            return
        pipe = self._redis.pipeline()
        for sid in sids:
            pipe.exists(self._skey(sid))
        existing = await pipe.execute()
        stale = [sid for sid, present in zip(sids, existing) if not present]
        if stale:
            await self._redis.zrem(ukey, *stale)

    async def _enforce_cap(self, user_id: int, *, now: datetime | None = None) -> None:
        cap = self._settings.session_max_concurrent
        if cap < 1:
            return
        await self._prune_user_index(user_id)
        ukey = self._ukey(user_id)
        count = await self._redis.zcard(ukey)
        if self._settings.session_cap_policy == "reject":
            if count >= cap:
                raise SessionCapReached(
                    f"user {user_id} already has {count} active sessions (cap {cap})"
                )
            return
        # evict_oldest: keep at most cap-1 so the new session brings it to cap.
        to_remove = count - (cap - 1)
        if to_remove <= 0:
            return
        oldest = await self._redis.zrange(ukey, 0, to_remove - 1)
        pipe = self._redis.pipeline()
        for sid in oldest:
            pipe.delete(self._skey(sid))
            pipe.zrem(ukey, sid)
        await pipe.execute()
