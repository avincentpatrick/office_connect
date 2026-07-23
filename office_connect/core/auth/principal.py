"""The request principal — what ``AuthPrincipalMiddleware`` puts on ``request.state.user``.

A lightweight, frozen snapshot built from the Redis ``SessionRecord`` with **no
per-request DB hit**: everything the request pipeline needs (the actor id for the
audit chain, the idle tier, and the gating flags) is snapshotted into the session
record at login. Authorization that genuinely needs live DB state
(``require_permission``) runs only on the handful of admin routes, not on every
request — so a DB blip can never 401 the whole app.

The raw ``session_id`` is carried for server-side use only (touch / rotate /
revoke); it is NEVER serialized into a response body — clients see the
``session_id_hash`` handle instead.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # avoid an import cycle at runtime (session_store never imports us)
    from office_connect.core.auth.session_store import SessionRecord


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: int
    session_id: str  # raw sid — server-side only, never placed in a response body
    email: str
    permissions_version: int
    roles: tuple[str, ...]
    idle_tier: str
    is_privileged: bool
    must_change_password: bool
    mfa_authenticated: bool
    mfa_setup_required: bool

    @property
    def session_id_hash(self) -> str:
        """The public handle for this session (matches core_login_attempts)."""
        return hashlib.sha256(self.session_id.encode("utf-8")).hexdigest()

    @classmethod
    def from_record(cls, rec: SessionRecord) -> Principal:
        return cls(
            user_id=rec.user_id,
            session_id=rec.sid,
            email=rec.email,
            permissions_version=rec.permissions_version,
            roles=rec.roles,
            idle_tier=rec.idle_tier,
            is_privileged=rec.is_privileged,
            must_change_password=rec.must_change_password,
            mfa_authenticated=rec.mfa_authenticated,
            mfa_setup_required=rec.mfa_setup_required,
        )
