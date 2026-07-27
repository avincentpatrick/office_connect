"""RBAC administration endpoints (Stage B / Increment 3).

Grant/revoke roles (optionally org-scoped and time-bounded for delegation/OIC) and
read the role/permission catalog. Every route is gated on a permission STRING
(never a role name); the grant/revoke handlers delegate to ``core.rbac`` which
bumps ``permissions_version`` + refreshes live sessions so a change lands on the
target's next request.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core import rbac as rbac_service
from office_connect.core.api.schemas.auth import OkResponse
from office_connect.core.api.schemas.rbac import (
    GrantRoleRequest,
    PermissionSummary,
    RoleSummary,
    UserRoleSummary,
)
from office_connect.core.auth.dependencies import (
    get_permission_cache,
    get_session_store,
    require_permission,
)
from office_connect.core.auth.permission_cache import PermissionCache
from office_connect.core.auth.principal import Principal
from office_connect.core.auth.session_store import SessionStore
from office_connect.core.db import get_session
from office_connect.core.models import Permission, Role, UserRole

router = APIRouter()


@router.get("/rbac/roles", response_model=list[RoleSummary])
async def list_roles(
    _: Principal = Depends(require_permission("rbac.role.read")),
    session: AsyncSession = Depends(get_session),
):
    roles = (
        await session.execute(select(Role).order_by(Role.code))
    ).scalars().all()
    return [
        RoleSummary(
            id=r.id,
            code=r.code,
            name=r.name,
            is_system=r.is_system,
            is_active=r.is_active,
        )
        for r in roles
    ]


@router.get("/rbac/permissions", response_model=list[PermissionSummary])
async def list_permissions(
    _: Principal = Depends(require_permission("rbac.permission.read")),
    session: AsyncSession = Depends(get_session),
):
    perms = (
        await session.execute(select(Permission).order_by(Permission.code))
    ).scalars().all()
    return [
        PermissionSummary(id=p.id, code=p.code, name=p.name, category=p.category)
        for p in perms
    ]


@router.get("/rbac/users/{user_id}/roles", response_model=list[UserRoleSummary])
async def list_user_roles(
    user_id: int,
    _: Principal = Depends(require_permission("rbac.role.read")),
    session: AsyncSession = Depends(get_session),
):
    grants = (
        await session.execute(
            select(UserRole)
            .where(UserRole.user_id == user_id)
            .order_by(UserRole.id)
        )
    ).scalars().all()
    return [_to_summary(g) for g in grants]


@router.post("/rbac/users/{user_id}/roles", response_model=UserRoleSummary)
async def grant_role(
    user_id: int,
    body: GrantRoleRequest,
    request: Request,
    principal: Principal = Depends(require_permission("rbac.role.grant")),
    session: AsyncSession = Depends(get_session),
    store: SessionStore = Depends(get_session_store),
    cache: PermissionCache = Depends(get_permission_cache),
):
    grant = await rbac_service.grant_role(
        session,
        store,
        cache,
        target_user_id=user_id,
        role_id=body.role_id,
        org_unit_id=body.org_unit_id,
        valid_from=body.valid_from,
        valid_to=body.valid_to,
        actor_id=principal.user_id,
        request_id=getattr(request.state, "request_id", None),
    )
    return _to_summary(grant)


@router.delete("/rbac/users/{user_id}/roles/{grant_id}", response_model=OkResponse)
async def revoke_role(
    user_id: int,
    grant_id: int,
    request: Request,
    principal: Principal = Depends(require_permission("rbac.role.revoke")),
    session: AsyncSession = Depends(get_session),
    store: SessionStore = Depends(get_session_store),
    cache: PermissionCache = Depends(get_permission_cache),
):
    await rbac_service.revoke_role(
        session,
        store,
        cache,
        target_user_id=user_id,
        grant_id=grant_id,
        actor_id=principal.user_id,
        request_id=getattr(request.state, "request_id", None),
    )
    return OkResponse()


def _to_summary(g: UserRole) -> UserRoleSummary:
    return UserRoleSummary(
        id=g.id,
        user_id=g.user_id,
        role_id=g.role_id,
        org_unit_id=g.org_unit_id,
        valid_from=g.valid_from,
        valid_to=g.valid_to,
    )
