"""Auth HTTP endpoints — cookie sessions, MFA, password change, session admin.

Thin translation of ``core/auth/service`` results into HTTP status + Set-Cookie +
the api-standards §3 error envelope. Login / MFA-verify open their OWN
``SessionLocal`` (at that point ``request.state.user`` is None, so the service
self-attributes its audited write to the authenticated user); every other endpoint
uses ``Depends(get_session)`` (the auth middleware already put the actor on
``request.state.user``, so ``get_session`` injects it).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.api.errors import APIError
from office_connect.core.api.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    MeResponse,
    MfaConfirmRequest,
    MfaEnrollResponse,
    MfaVerifyRequest,
    OkResponse,
    RevokedResponse,
    SessionSummary,
    TempPasswordResponse,
)
from office_connect.core.audit import append_auth_event
from office_connect.core.auth import mfa, service
from office_connect.core.auth.dependencies import (
    get_session_store,
    require_permission,
    require_session,
    require_session_pending_ok,
)
from office_connect.core.auth.password_policy import (
    PasswordPolicyError,
    normalize_password,
)
from office_connect.core.auth.principal import Principal
from office_connect.core.auth.service import LoginStatus
from office_connect.core.auth.session_store import SessionStore
from office_connect.core.auth.throttle import LoginThrottle
from office_connect.core.config import Settings, get_settings
from office_connect.core.db import SessionLocal, get_session
from office_connect.core.models import User
from office_connect.core.security import generate_temp_password, hash_password
from office_connect.core.time import utc_now

router = APIRouter()


def _client_ip(request: Request) -> str | None:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else None


def _set_session_cookie(response: Response, sid: str, settings: Settings) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=sid,
        httponly=True,
        secure=settings.resolved_cookie_secure,
        samesite=settings.session_cookie_samesite,
        path=settings.session_cookie_path,
        domain=settings.session_cookie_domain,
    )


def _clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.session_cookie_name,
        path=settings.session_cookie_path,
        domain=settings.session_cookie_domain,
    )


def _login_response(result, settings, response: Response) -> LoginResponse:
    _set_session_cookie(response, result.sid, settings)
    status = "authenticated"
    if result.must_change_password:
        status = "password_change_required"
    elif result.mfa_setup_required:
        status = "mfa_setup_required"
    return LoginResponse(
        status=status,
        user_id=result.user_id,
        must_change_password=result.must_change_password,
        mfa_setup_required=result.mfa_setup_required,
    )


@router.post("/auth/login", response_model=LoginResponse)
async def login(request: Request, response: Response, body: LoginRequest):
    settings = get_settings()
    store: SessionStore = request.app.state.session_store
    redis = request.app.state.session_redis
    throttle = LoginThrottle(redis, settings)
    async with SessionLocal() as db:
        result = await service.login(
            db, store, throttle, redis,
            identifier=body.identifier,
            password=body.password,
            ip=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
            request_id=getattr(request.state, "request_id", None),
        )
    if result.status is LoginStatus.THROTTLED:
        raise APIError(
            429, "too_many_attempts", "Too many attempts. Please try again later.",
            headers={"Retry-After": str(result.retry_after)},
        )
    if result.status is LoginStatus.INVALID:
        raise APIError(401, "invalid_credentials", "Invalid credentials.")
    if result.status is LoginStatus.MFA_REQUIRED:
        return LoginResponse(
            status="mfa_required", user_id=result.user_id, mfa_token=result.mfa_token
        )
    return _login_response(result, settings, response)


@router.post("/auth/mfa/verify", response_model=LoginResponse)
async def mfa_verify(request: Request, response: Response, body: MfaVerifyRequest):
    settings = get_settings()
    store: SessionStore = request.app.state.session_store
    redis = request.app.state.session_redis
    async with SessionLocal() as db:
        result = await service.complete_mfa(
            db, store, redis,
            mfa_token=body.mfa_token,
            code=body.code,
            ip=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
            request_id=getattr(request.state, "request_id", None),
        )
    if result.status is LoginStatus.INVALID:
        raise APIError(401, "invalid_credentials", "Invalid credentials.")
    if result.status is LoginStatus.MFA_FAILED:
        raise APIError(401, "mfa_failed", "Invalid authentication code.")
    return _login_response(result, settings, response)


@router.post("/auth/logout", response_model=OkResponse)
async def logout(
    request: Request,
    response: Response,
    principal: Principal = Depends(require_session_pending_ok),
    session: AsyncSession = Depends(get_session),
    store: SessionStore = Depends(get_session_store),
):
    await service.logout(
        session, store,
        user_id=principal.user_id,
        session_id=principal.session_id,
        ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        request_id=getattr(request.state, "request_id", None),
    )
    _clear_session_cookie(response, get_settings())
    return OkResponse()


@router.get("/auth/me", response_model=MeResponse)
async def me(
    principal: Principal = Depends(require_session_pending_ok),
    store: SessionStore = Depends(get_session_store),
):
    rec = await store.get_session_record(principal.session_id)
    if rec is None:
        raise APIError(401, "unauthorized", "Authentication required.")
    return MeResponse(
        user_id=principal.user_id,
        email=principal.email,
        roles=list(principal.roles),
        idle_tier=principal.idle_tier,
        is_privileged=principal.is_privileged,
        must_change_password=principal.must_change_password,
        mfa_authenticated=principal.mfa_authenticated,
        mfa_setup_required=principal.mfa_setup_required,
        session=SessionSummary(
            session_id_hash=principal.session_id_hash,
            created_at=rec.created_at,
            last_seen_at=rec.last_seen_at,
            ip=rec.ip,
            user_agent=rec.user_agent,
            current=True,
        ),
    )


@router.post("/auth/password/change", response_model=OkResponse)
async def change_password(
    request: Request,
    response: Response,
    body: ChangePasswordRequest,
    principal: Principal = Depends(require_session_pending_ok),
    session: AsyncSession = Depends(get_session),
    store: SessionStore = Depends(get_session_store),
):
    try:
        new_sid = await service.change_password(
            session, store,
            user_id=principal.user_id,
            session_id=principal.session_id,
            current_password=body.current_password,
            new_password=body.new_password,
            request_id=getattr(request.state, "request_id", None),
        )
    except PasswordPolicyError as exc:
        raise APIError(
            422, "password_policy",
            "Password does not meet the policy.",
            details=exc.errors,
        )
    _set_session_cookie(response, new_sid, get_settings())
    return OkResponse()


@router.post("/auth/mfa/enroll", response_model=MfaEnrollResponse)
async def mfa_enroll(
    principal: Principal = Depends(require_session_pending_ok),
    session: AsyncSession = Depends(get_session),
):
    settings = get_settings()
    user = (
        await session.execute(select(User).where(User.id == principal.user_id))
    ).scalar_one_or_none()
    if user is None:
        raise APIError(401, "unauthorized", "Authentication required.")
    secret = mfa.generate_secret()
    user.mfa_secret = secret
    user.mfa_enabled = False  # unconfirmed until a valid code is presented
    await session.commit()
    return MfaEnrollResponse(
        secret=secret,
        otpauth_uri=mfa.provisioning_uri(secret, user.email, settings.mfa_issuer),
    )


@router.post("/auth/mfa/confirm", response_model=OkResponse)
async def mfa_confirm(
    response: Response,
    body: MfaConfirmRequest,
    principal: Principal = Depends(require_session_pending_ok),
    session: AsyncSession = Depends(get_session),
    store: SessionStore = Depends(get_session_store),
):
    settings = get_settings()
    user = (
        await session.execute(select(User).where(User.id == principal.user_id))
    ).scalar_one_or_none()
    if user is None or not user.mfa_secret:
        raise APIError(400, "mfa_not_enrolled", "No pending MFA enrollment.")
    if not mfa.verify_code(user.mfa_secret, body.code, valid_window=settings.mfa_valid_window):
        raise APIError(401, "mfa_failed", "Invalid authentication code.")
    user.mfa_enabled = True
    await session.commit()  # audited: mfa_enabled False -> True (secret redacted)
    rotated = await store.regenerate_id(
        principal.session_id,
        mfa_setup_required=False,
        mfa_authenticated=True,
        last_auth_at=utc_now(),
    )
    if rotated is not None:
        _set_session_cookie(response, rotated[0], settings)
    return OkResponse()


@router.get("/auth/sessions", response_model=list[SessionSummary])
async def my_sessions(
    principal: Principal = Depends(require_session),
    store: SessionStore = Depends(get_session_store),
):
    recs = await store.list_for_user(principal.user_id)
    return [
        SessionSummary(
            session_id_hash=r.session_id_hash,
            created_at=r.created_at,
            last_seen_at=r.last_seen_at,
            ip=r.ip,
            user_agent=r.user_agent,
            current=(r.sid == principal.session_id),
        )
        for r in recs
    ]


@router.delete("/auth/sessions/{session_id_hash}", response_model=OkResponse)
async def revoke_my_session(
    session_id_hash: str,
    request: Request,
    response: Response,
    principal: Principal = Depends(require_session),
    session: AsyncSession = Depends(get_session),
    store: SessionStore = Depends(get_session_store),
):
    sid = await store.resolve_handle(principal.user_id, session_id_hash)
    if sid is None:
        raise APIError(404, "not_found", "Session not found.")
    await store.destroy(sid, user_id=principal.user_id)
    await append_auth_event(
        session,
        event="auth.session.revoked",
        subject_user_id=principal.user_id,
        actor_id=principal.user_id,
        request_id=getattr(request.state, "request_id", None),
        data={"reason": "self_revoke", "session_id_hash": session_id_hash},
    )
    await session.commit()
    if sid == principal.session_id:
        _clear_session_cookie(response, get_settings())
    return OkResponse()


@router.get("/auth/users/{user_id}/sessions", response_model=list[SessionSummary])
async def user_sessions(
    user_id: int,
    _: Principal = Depends(require_permission("session.read")),
    store: SessionStore = Depends(get_session_store),
):
    recs = await store.list_for_user(user_id)
    return [
        SessionSummary(
            session_id_hash=r.session_id_hash,
            created_at=r.created_at,
            last_seen_at=r.last_seen_at,
            ip=r.ip,
            user_agent=r.user_agent,
        )
        for r in recs
    ]


@router.delete("/auth/users/{user_id}/sessions", response_model=RevokedResponse)
async def revoke_user_sessions(
    user_id: int,
    request: Request,
    principal: Principal = Depends(require_permission("session.revoke")),
    session: AsyncSession = Depends(get_session),
    store: SessionStore = Depends(get_session_store),
):
    revoked = await store.destroy_all_for_user(user_id)
    await append_auth_event(
        session,
        event="auth.session.revoked",
        subject_user_id=user_id,
        actor_id=principal.user_id,
        request_id=getattr(request.state, "request_id", None),
        data={"reason": "admin_revoke", "revoked_count": revoked},
    )
    await session.commit()
    return RevokedResponse(revoked=revoked)


@router.post(
    "/auth/users/{user_id}/reset-password", response_model=TempPasswordResponse
)
async def admin_reset_password(
    user_id: int,
    principal: Principal = Depends(require_permission("user.password.reset")),
    session: AsyncSession = Depends(get_session),
    store: SessionStore = Depends(get_session_store),
):
    user = (
        await session.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if user is None:
        raise APIError(404, "not_found", "User not found.")
    temp = generate_temp_password()
    user.password_hash = hash_password(normalize_password(temp))
    user.must_change_password = True
    user.password_changed_at = utc_now()
    await session.flush()  # the password.reset chain row (secret redacted)
    revoked = await store.destroy_all_for_user(user_id)
    await append_auth_event(
        session,
        event="auth.session.revoked",
        subject_user_id=user_id,
        actor_id=principal.user_id,
        data={"reason": "password_reset", "revoked_count": revoked},
    )
    await session.commit()
    return TempPasswordResponse(temporary_password=temp)
