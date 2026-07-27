"""Admin user-provisioning endpoints (Stage B / Increment 4).

Admin-managed account lifecycle (auth-rbac-onprem.md) — **no self-registration**.
Create mints a login from an existing staff record with a temporary password
(forced change on first login); deactivate flips ``is_active`` AND revokes every
Redis session immediately; every event is hash-chained with the acting admin.
Role assignment reuses the RBAC router (``/rbac/users/{id}/roles``); password reset
reuses ``/auth/users/{id}/reset-password`` — not duplicated here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.api.errors import APIError
from office_connect.core.api.schemas.users import (
    CreatedUserResponse,
    CreateUserRequest,
    DeactivateResponse,
    UserSummary,
)
from office_connect.core.audit import append_auth_event
from office_connect.core.auth.dependencies import get_session_store, require_permission
from office_connect.core.auth.password_policy import normalize_password
from office_connect.core.auth.principal import Principal
from office_connect.core.auth.session_store import SessionStore
from office_connect.core.db import get_session
from office_connect.core.models import Staff, User
from office_connect.core.security import generate_temp_password, hash_password

router = APIRouter()


def _summary(u: User) -> UserSummary:
    return UserSummary(
        id=u.id,
        email=u.email,
        is_active=u.is_active,
        is_break_glass=u.is_break_glass,
        must_change_password=u.must_change_password,
        auth_source=u.auth_source,
        staff_id=u.staff_id,
        last_login_at=u.last_login_at,
        created_at=u.created_at,
    )


@router.post("/users", response_model=CreatedUserResponse, status_code=201)
async def create_user(
    body: CreateUserRequest,
    request: Request,
    principal: Principal = Depends(require_permission("user.create")),
    session: AsyncSession = Depends(get_session),
):
    staff = (
        await session.execute(select(Staff).where(Staff.id == body.staff_id))
    ).scalar_one_or_none()
    if staff is None:
        raise APIError(404, "not_found", "Staff record not found.")
    email = body.email or staff.email
    if not email:
        raise APIError(
            422, "validation_error", "An email is required (the staff record has none)."
        )
    if (
        await session.execute(select(User.id).where(User.email == email))
    ).scalar_one_or_none() is not None:
        raise APIError(409, "conflict", "A user with that email already exists.")
    if (
        await session.execute(select(User.id).where(User.staff_id == body.staff_id))
    ).scalar_one_or_none() is not None:
        raise APIError(409, "conflict", "That staff member already has a login.")

    temp = generate_temp_password()
    user = User(
        email=email,
        password_hash=hash_password(normalize_password(temp)),
        must_change_password=True,
        is_active=True,
        is_break_glass=False,
        auth_source="local",
        staff_id=body.staff_id,
    )
    session.add(user)
    await session.flush()  # INSERT auto-audited (password_hash redacted)
    await append_auth_event(
        session,
        event="user.created",
        subject_user_id=user.id,
        actor_id=principal.user_id,
        request_id=getattr(request.state, "request_id", None),
        table_name="core_users",
        row_pk=user.id,
        data={"staff_id": body.staff_id, "email": email},
    )
    await session.commit()
    return CreatedUserResponse(user_id=user.id, email=email, temporary_password=temp)


@router.get("/users", response_model=list[UserSummary])
async def list_users(
    q: str | None = None,
    is_active: bool | None = None,
    limit: int = 50,
    offset: int = 0,
    _: Principal = Depends(require_permission("user.read")),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(User).order_by(User.id)
    if q:
        stmt = stmt.where(User.email.ilike(f"%{q}%"))
    if is_active is not None:
        stmt = stmt.where(User.is_active == is_active)
    stmt = stmt.limit(min(limit, 200)).offset(max(offset, 0))
    users = (await session.execute(stmt)).scalars().all()
    return [_summary(u) for u in users]


@router.get("/users/{user_id}", response_model=UserSummary)
async def get_user(
    user_id: int,
    _: Principal = Depends(require_permission("user.read")),
    session: AsyncSession = Depends(get_session),
):
    user = (
        await session.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if user is None:
        raise APIError(404, "not_found", "User not found.")
    return _summary(user)


@router.post("/users/{user_id}/deactivate", response_model=DeactivateResponse)
async def deactivate_user(
    user_id: int,
    request: Request,
    principal: Principal = Depends(require_permission("user.deactivate")),
    session: AsyncSession = Depends(get_session),
    store: SessionStore = Depends(get_session_store),
):
    if user_id == principal.user_id:
        raise APIError(409, "conflict", "You cannot deactivate your own account.")
    user = (
        await session.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if user is None:
        raise APIError(404, "not_found", "User not found.")
    if user.is_break_glass:
        raise APIError(
            409, "conflict", "The break-glass admin account cannot be deactivated."
        )
    user.is_active = False
    await session.flush()  # is_active UPDATE audited
    revoked = await store.destroy_all_for_user(user_id)  # kill all sessions now
    await append_auth_event(
        session,
        event="user.deactivated",
        subject_user_id=user_id,
        actor_id=principal.user_id,
        request_id=getattr(request.state, "request_id", None),
        table_name="core_users",
        row_pk=user_id,
        data={"sessions_revoked": revoked},
    )
    await session.commit()
    return DeactivateResponse(user_id=user_id, is_active=False, sessions_revoked=revoked)


@router.post("/users/{user_id}/reactivate", response_model=UserSummary)
async def reactivate_user(
    user_id: int,
    request: Request,
    principal: Principal = Depends(require_permission("user.deactivate")),
    session: AsyncSession = Depends(get_session),
):
    user = (
        await session.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if user is None:
        raise APIError(404, "not_found", "User not found.")
    user.is_active = True  # idempotent; does not touch password or sessions
    await session.flush()
    await append_auth_event(
        session,
        event="user.reactivated",
        subject_user_id=user_id,
        actor_id=principal.user_id,
        request_id=getattr(request.state, "request_id", None),
        table_name="core_users",
        row_pk=user_id,
    )
    await session.commit()
    return _summary(user)
