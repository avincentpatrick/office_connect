"""FastAPI auth dependencies — the 401/403 gates for protected routes.

``AuthPrincipalMiddleware`` sets ``request.state.user``; these dependencies turn
that into route-level access control:

- ``require_session`` — 401 if anonymous, then enforces the *gates* (a session
  flagged ``must_change_password`` or ``mfa_setup_required`` is 403'd) so a
  long-lived session can't skip them. This is the default for protected routes.
- ``require_session_pending_ok`` — 401 if anonymous but skips the gates; used by
  the few routes reachable while pending (logout, me, password/change, mfa setup).
- ``require_permission(perm)`` — B2's MINIMAL, uncached authorization: one ORM
  query over live (soft-delete-filtered, valid-window) grants. B3 swaps the
  internals for the Redis-cached, org-scoped resolver behind this same signature.
- ``require_reauth`` — re-reads the session's ``last_auth_at`` and 401s if the
  credential proof is stale (high-impact actions).
"""

from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.api.errors import APIError
from office_connect.core.auth import policy
from office_connect.core.auth.principal import Principal
from office_connect.core.auth.session_store import SessionStore
from office_connect.core.config import get_settings
from office_connect.core.db import get_session
from office_connect.core.models import Permission, RolePermission, UserRole
from office_connect.core.time import utc_now


def get_session_store(request: Request) -> SessionStore:
    store = getattr(request.app.state, "session_store", None)
    if store is None:  # lifespan didn't run / Redis missing — fail visibly, not 500
        raise APIError(503, "unavailable", "The session store is not available.")
    return store


def current_user(request: Request) -> Principal | None:
    """The authenticated principal, or None — never raises."""
    return getattr(request.state, "user", None)


def require_session_pending_ok(request: Request) -> Principal:
    user = getattr(request.state, "user", None)
    if user is None:
        raise APIError(401, "unauthorized", "Authentication required.")
    return user


def require_session(request: Request) -> Principal:
    user = require_session_pending_ok(request)
    if user.must_change_password:
        raise APIError(
            403,
            "password_change_required",
            "You must change your password before continuing.",
        )
    if user.mfa_setup_required:
        raise APIError(
            403,
            "mfa_setup_required",
            "You must set up multi-factor authentication before continuing.",
        )
    return user


async def effective_permissions(session: AsyncSession, user_id: int) -> set[str]:
    """Permission codes a user currently holds (any org scope). Soft-deleted
    grants/roles/permissions are excluded by the global filter; the time window
    (``valid_from``/``valid_to``) is honored here for B3 delegation grants."""
    now = utc_now()
    stmt = (
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(
            UserRole.user_id == user_id,
            or_(UserRole.valid_from.is_(None), UserRole.valid_from <= now),
            or_(UserRole.valid_to.is_(None), UserRole.valid_to > now),
        )
    )
    return set((await session.execute(stmt)).scalars().all())


def require_permission(perm: str):
    async def _dep(
        principal: Principal = Depends(require_session),
        session: AsyncSession = Depends(get_session),
    ) -> Principal:
        if perm not in await effective_permissions(session, principal.user_id):
            raise APIError(403, "forbidden", "You do not have permission to do that.")
        return principal

    return _dep


async def require_reauth(
    principal: Principal = Depends(require_session_pending_ok),
    store: SessionStore = Depends(get_session_store),
) -> Principal:
    rec = await store.get_session_record(principal.session_id)
    if rec is None:
        raise APIError(401, "unauthorized", "Authentication required.")
    if policy.reauth_required(rec.last_auth_at, settings=get_settings()):
        raise APIError(
            401, "reauth_required", "Please re-authenticate to perform this action."
        )
    return principal
