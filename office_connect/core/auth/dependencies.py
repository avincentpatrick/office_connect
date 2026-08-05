"""FastAPI auth dependencies — the 401/403 gates for protected routes.

``AuthPrincipalMiddleware`` sets ``request.state.user``; these dependencies turn
that into route-level access control:

- ``require_session`` — 401 if anonymous, then enforces the *gates* (a session
  flagged ``must_change_password`` or ``mfa_setup_required`` is 403'd) so a
  long-lived session can't skip them. This is the default for protected routes.
- ``require_session_pending_ok`` — 401 if anonymous but skips the gates; used by
  the few routes reachable while pending (logout, me, password/change, mfa setup).
- ``require_permission(perm, scope=...)`` — B3's authorization gate. The default
  ``scope=GLOBAL`` resolves the actor's effective permission set from the
  **Redis cache** (keyed by ``permissions_version``; a cache hit takes NO DB hit)
  and 403s if ``perm`` is absent — same signature the B2 admin routes already use.
  ``scope=REQUESTER`` runs an uncached, org-scoped check (``authorize_scoped``)
  against the request's org unit. Authorization is on permission STRINGS, never
  role names.
- ``require_reauth`` — re-reads the session's ``last_auth_at`` and 401s if the
  credential proof is stale (high-impact actions).
- ``require_feature(flag_key)`` — the module-surface gate (R-2-wizard): 404
  unless the feature flag is ON. Declared at router level on module routers so
  an OFF module is indistinguishable from absent (fail-safe OFF).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from fastapi import Depends, Request
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.api.errors import APIError
from office_connect.core.auth import policy
from office_connect.core.auth.permission_cache import PermissionCache
from office_connect.core.auth.principal import Principal
from office_connect.core.auth.session_store import SessionStore
from office_connect.core.config import get_settings
from office_connect.core.db import SessionLocal
from office_connect.core.models import (
    FeatureFlag,
    Permission,
    RolePermission,
    UserRole,
)
from office_connect.core.org_units import OrgUnitScope, authorize_scoped
from office_connect.core.time import utc_now


def get_session_store(request: Request) -> SessionStore:
    store = getattr(request.app.state, "session_store", None)
    if store is None:  # lifespan didn't run / Redis missing — fail visibly, not 500
        raise APIError(503, "unavailable", "The session store is not available.")
    return store


def get_permission_cache(request: Request) -> PermissionCache:
    cache = getattr(request.app.state, "permission_cache", None)
    if cache is None:  # lifespan didn't run / Redis missing — fail visibly, not 500
        raise APIError(503, "unavailable", "The permission cache is not available.")
    return cache


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


async def load_permission_entry(
    session: AsyncSession, user_id: int
) -> tuple[set[str], datetime | None]:
    """The cache loader: the user's currently-active permission codes AND the next
    valid-window edge (soonest ``valid_from``/``valid_to`` in the future) so the
    cache TTL drops the entry exactly when a delegation/OIC grant opens or closes.
    Soft-deleted grants/roles/permissions are excluded by the global filter."""
    now = utc_now()
    stmt = (
        select(Permission.code, UserRole.valid_from, UserRole.valid_to)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(UserRole.user_id == user_id)
    )
    codes: set[str] = set()
    boundaries: list[datetime] = []
    for code, valid_from, valid_to in (await session.execute(stmt)).all():
        if (valid_from is None or valid_from <= now) and (
            valid_to is None or valid_to > now
        ):
            codes.add(code)
        if valid_from is not None and valid_from > now:
            boundaries.append(valid_from)
        if valid_to is not None and valid_to > now:
            boundaries.append(valid_to)
    return codes, (min(boundaries) if boundaries else None)


def require_permission(
    perm: str,
    scope: OrgUnitScope = OrgUnitScope.GLOBAL,
    *,
    org_unit_getter: Callable[[Request], int | None] | None = None,
):
    """Dependency factory: 403 unless the actor holds ``perm``.

    ``scope=GLOBAL`` (default) — read the effective set from the Redis cache
    (no DB on a hit; a miss lazily loads via ``load_permission_entry``). Identical
    semantics to B2 for the existing admin routes. ``scope=REQUESTER`` — the
    request's target org unit (``org_unit_getter(request)``, else
    ``request.state.scope_org_unit_id``) is checked against the actor's scoped
    grants (uncached, fresh DB — approval decisions must never read stale org data).

    The returned dependency carries ``oc_permission`` / ``oc_scope`` so a test
    can read a route's *declared* gate out of the running app rather than out of
    the source (R-9's authorization census —
    ``tests/test_reimb_authz_census.py``). A closure is opaque to introspection;
    two attributes turn the wiring into a fact the suite can assert on instead
    of a string it has to grep for.
    """

    async def _dep(
        request: Request,
        principal: Principal = Depends(require_session),
        cache: PermissionCache = Depends(get_permission_cache),
    ) -> Principal:
        if scope is OrgUnitScope.GLOBAL:

            async def _loader() -> tuple[set[str], datetime | None]:
                async with SessionLocal() as session:
                    return await load_permission_entry(session, principal.user_id)

            codes = await cache.get_or_load(
                principal.user_id, principal.permissions_version, _loader
            )
            if perm not in codes:
                raise APIError(
                    403, "forbidden", "You do not have permission to do that."
                )
            return principal

        target = (
            org_unit_getter(request)
            if org_unit_getter is not None
            else getattr(request.state, "scope_org_unit_id", None)
        )
        async with SessionLocal() as session:
            if not await authorize_scoped(
                session, principal.user_id, perm, target
            ):
                raise APIError(
                    403, "forbidden", "You do not have permission to do that."
                )
        return principal

    _dep.oc_permission = perm
    _dep.oc_scope = scope
    return _dep


def require_feature(flag_key: str):
    """Dependency factory: 404 unless the ``flag_key`` feature flag is ON
    (``enabled AND is_active`` on a live row — the same rule as the workflow
    engine's flag gate and ``/api/v1/config``). Fail-safe OFF: a missing row
    404s too, so a gated module surface is indistinguishable from absent
    (api-standards §9). Takes a plain string so core stays module-agnostic.
    Uncached — one indexed select per request; a Redis-backed variant is a
    recorded deferral. Note the flag blocks the SURFACE only; the workflow
    engine separately lets in-flight instances finish (workflow-standards §9)."""

    async def _dep() -> None:
        async with SessionLocal() as session:
            row = (
                await session.execute(
                    select(FeatureFlag).where(FeatureFlag.key == flag_key)
                )
            ).scalar_one_or_none()
        if not (row and row.enabled and row.is_active):
            raise APIError(404, "not_found", "Not found.")

    # Same introspection contract as ``require_permission`` above: the R-9
    # census reads which flag a route sits behind (or that it sits behind none)
    # off the app, so a router mounted without its gate fails a test instead of
    # merely looking fine in review.
    _dep.oc_feature_flag = flag_key
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
