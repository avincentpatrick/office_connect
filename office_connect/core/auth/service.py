"""Authentication service — the login / MFA / logout / password-change state
machine (auth-rbac-onprem.md). Pure of FastAPI: it takes an ``AsyncSession`` and
the Redis-backed collaborators, so it is unit-testable with the ``app_session``
fixture + real Redis. The API layer (``core/api/auth.py``) translates the returned
``LoginResult`` into HTTP status + Set-Cookie.

Anti-enumeration is baked in: an unknown identifier and a wrong password take the
same time (a dummy Argon2 verify burns the work) and return the SAME generic
failure; throttle counters increment regardless of whether the account exists.
Every branch writes a ``core_login_attempts`` row (the login event log) with the
IP + user-agent + a COARSE reason — never the password.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from enum import Enum

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.api.errors import APIError
from office_connect.core.audit import append_auth_event
from office_connect.core.auth import mfa
from office_connect.core.auth.password_policy import (
    normalize_password,
    validate_password,
)
from office_connect.core.auth.session_store import SessionStore
from office_connect.core.auth.throttle import LoginThrottle
from office_connect.core.auth.verifiers import select_verifier
from office_connect.core.config import get_settings
from office_connect.core.models import LoginAttempt, Role, User, UserRole
from office_connect.core.security import hash_password, needs_rehash, verify_password
from office_connect.core.session import set_audit_context
from office_connect.core.time import utc_now

# A real Argon2 hash to verify against when the account is unknown / has no local
# credential, so timing can't distinguish "no such account" (computed once).
_DUMMY_HASH = hash_password(secrets.token_urlsafe(32))
_PENDING_PREFIX = "mfa:pending:"


class LoginStatus(str, Enum):
    SUCCESS = "success"
    INVALID = "invalid"  # generic — unknown user / wrong password / inactive
    THROTTLED = "throttled"
    MFA_REQUIRED = "mfa_required"
    MFA_FAILED = "mfa_failed"


@dataclass(frozen=True, slots=True)
class LoginResult:
    status: LoginStatus
    sid: str | None = None
    user_id: int | None = None
    must_change_password: bool = False
    mfa_setup_required: bool = False
    mfa_token: str | None = None
    retry_after: int = 0


def _sid_hash(sid: str) -> str:
    return hashlib.sha256(sid.encode("utf-8")).hexdigest()


async def _record_attempt(
    session: AsyncSession,
    *,
    user_id: int | None,
    identifier: str,
    outcome: str,
    ip: str | None,
    user_agent: str | None,
    failure_reason: str | None = None,
    session_id_hash: str | None = None,
) -> None:
    session.add(
        LoginAttempt(
            user_id=user_id,
            attempted_identifier=(identifier or "")[:320],
            outcome=outcome,
            failure_reason=failure_reason,
            ip_address=ip,
            user_agent=user_agent,
            session_id_hash=session_id_hash,
        )
    )


async def _role_codes(session: AsyncSession, user_id: int) -> set[str]:
    now = utc_now()
    stmt = (
        select(Role.code)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(
            UserRole.user_id == user_id,
            or_(UserRole.valid_from.is_(None), UserRole.valid_from <= now),
            or_(UserRole.valid_to.is_(None), UserRole.valid_to > now),
        )
    )
    return set((await session.execute(stmt)).scalars().all())


def _requires_mfa(role_codes, settings) -> bool:
    return bool(set(role_codes) & set(settings.mfa_required_role_codes))


async def _put_pending(redis, token: str, *, user_id: int, ip: str | None, ttl: int) -> None:
    key = f"{_PENDING_PREFIX}{token}"
    await redis.hset(key, mapping={"user_id": str(user_id), "ip": ip or ""})
    await redis.expire(key, ttl)


async def _get_pending(redis, token: str) -> dict[str, str] | None:
    return (await redis.hgetall(f"{_PENDING_PREFIX}{token}")) or None


async def _delete_pending(redis, token: str) -> None:
    await redis.delete(f"{_PENDING_PREFIX}{token}")


async def _create_session_for(
    session: AsyncSession,
    store: SessionStore,
    user: User,
    roles: tuple[str, ...],
    *,
    ip: str | None,
    user_agent: str | None,
    mfa_setup_required: bool,
) -> LoginResult:
    """Shared success tail: stamp last_login, create the session, log success."""
    user.last_login_at = utc_now()
    sid, _rec = await store.create_session(
        user_id=user.id,
        email=user.email,
        permissions_version=user.permissions_version,
        roles=roles,
        ip=ip,
        user_agent=user_agent,
        must_change_password=user.must_change_password,
        mfa_setup_required=mfa_setup_required,
        mfa_authenticated=True,
    )
    await _record_attempt(
        session,
        user_id=user.id,
        identifier=user.email,
        outcome="success",
        ip=ip,
        user_agent=user_agent,
        session_id_hash=_sid_hash(sid),
    )
    await session.commit()
    return LoginResult(
        LoginStatus.SUCCESS,
        sid=sid,
        user_id=user.id,
        must_change_password=user.must_change_password,
        mfa_setup_required=mfa_setup_required,
    )


async def login(
    session: AsyncSession,
    store: SessionStore,
    throttle: LoginThrottle,
    redis,
    *,
    identifier: str,
    password: str,
    ip: str | None,
    user_agent: str | None,
    request_id: str | None = None,
) -> LoginResult:
    settings = get_settings()
    ident = (identifier or "").strip()

    decision = await throttle.check(ident, ip)
    if not decision.allowed:
        await _record_attempt(
            session, user_id=None, identifier=ident, outcome="throttled",
            failure_reason="throttled", ip=ip, user_agent=user_agent,
        )
        await session.commit()
        return LoginResult(LoginStatus.THROTTLED, retry_after=decision.retry_after)

    user = (
        await session.execute(select(User).where(func.lower(User.email) == ident.lower()))
    ).scalar_one_or_none()

    normalized_pw = normalize_password(password or "")
    if user is not None and user.password_hash:
        ok = select_verifier(user).verify(user, normalized_pw)
    else:
        verify_password(normalized_pw, _DUMMY_HASH)  # constant-time: burn the work
        ok = False

    if user is None or not ok or not user.is_active:
        await throttle.register_failure(ident, ip)
        reason = "bad_credentials" if (user is None or not ok) else "inactive"
        await _record_attempt(
            session, user_id=(user.id if user else None), identifier=ident,
            outcome="failure", failure_reason=reason, ip=ip, user_agent=user_agent,
        )
        await session.commit()
        return LoginResult(LoginStatus.INVALID)

    # Password proven — from here writes attribute to the authenticated user.
    await throttle.reset(ident, ip)
    set_audit_context(session, actor_id=user.id, request_id=request_id)
    if user.password_hash and needs_rehash(user.password_hash):
        user.password_hash = hash_password(normalized_pw)  # transparent cost upgrade

    roles = tuple(await _role_codes(session, user.id))

    if user.mfa_enabled:
        token = secrets.token_urlsafe(24)
        await _put_pending(
            redis, token, user_id=user.id, ip=ip,
            ttl=settings.session_reauth_seconds,
        )
        await _record_attempt(
            session, user_id=user.id, identifier=ident, outcome="mfa_required",
            ip=ip, user_agent=user_agent,
        )
        await session.commit()
        return LoginResult(LoginStatus.MFA_REQUIRED, user_id=user.id, mfa_token=token)

    # No MFA secret yet but the role demands one → force enrollment (not a block).
    mfa_setup_required = _requires_mfa(roles, settings)
    return await _create_session_for(
        session, store, user, roles, ip=ip, user_agent=user_agent,
        mfa_setup_required=mfa_setup_required,
    )


async def complete_mfa(
    session: AsyncSession,
    store: SessionStore,
    redis,
    *,
    mfa_token: str,
    code: str,
    ip: str | None,
    user_agent: str | None,
    request_id: str | None = None,
) -> LoginResult:
    settings = get_settings()
    pending = await _get_pending(redis, mfa_token or "")
    if pending is None:
        return LoginResult(LoginStatus.INVALID)
    user = (
        await session.execute(select(User).where(User.id == int(pending["user_id"])))
    ).scalar_one_or_none()
    if user is None or not user.is_active or not user.mfa_enabled or not user.mfa_secret:
        return LoginResult(LoginStatus.INVALID)

    ok = await mfa.check_and_consume(
        redis, user.id, user.mfa_secret, code or "",
        valid_window=settings.mfa_valid_window,
    )
    if not ok:
        await _record_attempt(
            session, user_id=user.id, identifier=user.email, outcome="mfa_failure",
            ip=ip, user_agent=user_agent,
        )
        await session.commit()
        return LoginResult(LoginStatus.MFA_FAILED, user_id=user.id)

    await _delete_pending(redis, mfa_token)
    set_audit_context(session, actor_id=user.id, request_id=request_id)
    roles = tuple(await _role_codes(session, user.id))
    return await _create_session_for(
        session, store, user, roles, ip=ip, user_agent=user_agent,
        mfa_setup_required=False,
    )


async def logout(
    session: AsyncSession,
    store: SessionStore,
    *,
    user_id: int,
    session_id: str,
    ip: str | None,
    user_agent: str | None,
    request_id: str | None = None,
) -> None:
    await store.destroy(session_id, user_id=user_id)
    await append_auth_event(
        session,
        event="auth.logout",
        subject_user_id=user_id,
        actor_id=user_id,
        request_id=request_id,
        data={"session_id_hash": _sid_hash(session_id), "ip": ip},
    )
    await session.commit()


async def change_password(
    session: AsyncSession,
    store: SessionStore,
    *,
    user_id: int,
    session_id: str,
    current_password: str,
    new_password: str,
    request_id: str | None = None,
) -> str:
    """Change own password: verify current (reauth), validate the new one, update
    (audited, redacted), revoke ALL other sessions, and rotate the current sid.
    Returns the new sid so the caller can refresh the cookie. ``validate_password``
    raises ``PasswordPolicyError`` (the endpoint maps it to a 422 envelope)."""
    user = (
        await session.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if user is None or not user.is_active:
        raise APIError(401, "unauthorized", "Authentication required.")

    if not user.password_hash or not verify_password(
        normalize_password(current_password or ""), user.password_hash
    ):
        raise APIError(401, "invalid_credentials", "Current password is incorrect.")

    validate_password(new_password or "", email=user.email)

    set_audit_context(session, actor_id=user.id, request_id=request_id)
    user.password_hash = hash_password(normalize_password(new_password))
    user.must_change_password = False
    user.password_changed_at = utc_now()
    await session.flush()  # write the password.changed chain row BEFORE the revoke row

    revoked = await store.destroy_all_for_user(user.id, except_sid=session_id)
    rotated = await store.regenerate_id(
        session_id, must_change_password=False, last_auth_at=utc_now()
    )
    new_sid = rotated[0] if rotated else session_id

    await append_auth_event(
        session,
        event="auth.session.revoked",
        subject_user_id=user.id,
        actor_id=user.id,
        request_id=request_id,
        data={"reason": "password_change", "revoked_count": revoked},
    )
    await session.commit()
    return new_sid
