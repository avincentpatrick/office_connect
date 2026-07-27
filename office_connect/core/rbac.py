"""RBAC grant/revoke service (Stage B / Increment 3).

The admin operation that changes who holds what. Each grant/revoke:

1. mutates ``core_user_roles`` — insert (or restore a tombstoned grant), or
   soft-delete — so the change itself is an auditable business row;
2. bumps the target ``core_users.permissions_version`` (the cache-invalidation
   counter);
3. emits a semantic ``rbac.role.granted`` / ``rbac.role.revoked`` hash-chain event
   (``core/audit.py``);
4. commits, then propagates the new version to the target's **live sessions**
   (``SessionStore.set_permissions_version``) so the change lands on their NEXT
   request via a fresh permission-cache key — no re-login, no stale authority.

Redis is touched only AFTER the DB commit: were the commit to roll back, we must
not have already told sessions a version that never persisted.

``org_unit_id`` (NULL = global) and the ``valid_from`` / ``valid_to`` window
(delegation / OIC) are grant attributes — no separate delegation table
(foundation.md §5 B3).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.api.errors import APIError
from office_connect.core.audit import append_auth_event
from office_connect.core.auth.permission_cache import PermissionCache
from office_connect.core.auth.session_store import SessionStore
from office_connect.core.models import Role, User, UserRole
from office_connect.core.soft_delete import soft_delete


async def _bump_permissions_version(session: AsyncSession, user: User) -> int:
    user.permissions_version = (user.permissions_version or 0) + 1
    await session.flush()
    return user.permissions_version


async def grant_role(
    session: AsyncSession,
    store: SessionStore,
    cache: PermissionCache,
    *,
    target_user_id: int,
    role_id: int,
    org_unit_id: int | None = None,
    valid_from: datetime | None = None,
    valid_to: datetime | None = None,
    actor_id: int,
    request_id: str | None = None,
) -> UserRole:
    """Grant ``role_id`` to ``target_user_id`` (optionally org-scoped and/or
    time-bounded). Idempotent on the ``(user, role, org_unit)`` triple: restores a
    tombstoned grant, else inserts. Raises 404 if the user or role is absent."""
    user = (
        await session.execute(select(User).where(User.id == target_user_id))
    ).scalar_one_or_none()
    if user is None:
        raise APIError(404, "not_found", "User not found.")
    role = (
        await session.execute(select(Role).where(Role.id == role_id))
    ).scalar_one_or_none()
    if role is None:
        raise APIError(404, "not_found", "Role not found.")

    org_cond = (
        UserRole.org_unit_id.is_(None)
        if org_unit_id is None
        else UserRole.org_unit_id == org_unit_id
    )
    existing = (
        await session.execute(
            select(UserRole)
            .where(
                UserRole.user_id == target_user_id,
                UserRole.role_id == role_id,
                org_cond,
            )
            .execution_options(include_deleted=True)
        )
    ).scalar_one_or_none()

    if existing is None:
        grant = UserRole(
            user_id=target_user_id,
            role_id=role_id,
            org_unit_id=org_unit_id,
            valid_from=valid_from,
            valid_to=valid_to,
        )
        session.add(grant)
    else:
        grant = existing
        grant.deleted_at = None  # restore if tombstoned (no-op if already live)
        grant.deleted_by = None
        grant.valid_from = valid_from
        grant.valid_to = valid_to
    await session.flush()

    new_version = await _bump_permissions_version(session, user)
    await append_auth_event(
        session,
        event="rbac.role.granted",
        subject_user_id=target_user_id,
        actor_id=actor_id,
        request_id=request_id,
        table_name="core_user_roles",
        row_pk=grant.id,
        data={
            "role_id": role_id,
            "role_code": role.code,
            "org_unit_id": org_unit_id,
            "valid_from": valid_from,
            "valid_to": valid_to,
        },
    )
    await session.commit()
    await store.set_permissions_version(target_user_id, new_version)
    await cache.invalidate(target_user_id, new_version - 1)  # reclaim the dead key
    return grant


async def revoke_role(
    session: AsyncSession,
    store: SessionStore,
    cache: PermissionCache,
    *,
    target_user_id: int,
    grant_id: int,
    actor_id: int,
    request_id: str | None = None,
) -> UserRole:
    """Soft-delete the ``core_user_roles`` grant ``grant_id`` (a tombstone survives
    for audit). Raises 404 if it is not a live grant of ``target_user_id``."""
    grant = (
        await session.execute(
            select(UserRole).where(
                UserRole.id == grant_id, UserRole.user_id == target_user_id
            )
        )
    ).scalar_one_or_none()
    if grant is None:
        raise APIError(404, "not_found", "Role grant not found.")

    role_id, org_unit_id = grant.role_id, grant.org_unit_id
    soft_delete(grant, actor_id=actor_id)
    await session.flush()

    user = (
        await session.execute(select(User).where(User.id == target_user_id))
    ).scalar_one_or_none()
    if user is None:  # FK guarantees it exists, but stay defensive
        raise APIError(404, "not_found", "User not found.")
    new_version = await _bump_permissions_version(session, user)
    await append_auth_event(
        session,
        event="rbac.role.revoked",
        subject_user_id=target_user_id,
        actor_id=actor_id,
        request_id=request_id,
        table_name="core_user_roles",
        row_pk=grant_id,
        data={"role_id": role_id, "org_unit_id": org_unit_id},
    )
    await session.commit()
    await store.set_permissions_version(target_user_id, new_version)
    await cache.invalidate(target_user_id, new_version - 1)  # reclaim the dead key
    return grant
