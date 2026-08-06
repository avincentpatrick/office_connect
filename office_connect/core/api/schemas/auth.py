"""Auth endpoint request/response models (api-standards §2)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    identifier: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class MfaVerifyRequest(BaseModel):
    mfa_token: str = Field(min_length=1, max_length=256)
    code: str = Field(min_length=6, max_length=10)


class MfaConfirmRequest(BaseModel):
    code: str = Field(min_length=6, max_length=10)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=1, max_length=1024)


class LoginResponse(BaseModel):
    # status: authenticated | mfa_required | password_change_required | mfa_setup_required
    status: str
    user_id: int | None = None
    must_change_password: bool = False
    mfa_setup_required: bool = False
    mfa_token: str | None = None


class SessionSummary(BaseModel):
    session_id_hash: str
    created_at: datetime
    last_seen_at: datetime
    ip: str | None = None
    user_agent: str | None = None
    current: bool = False


class MeResponse(BaseModel):
    user_id: int
    email: str
    #: Role codes from the session snapshot — NOT a gate. They are stamped at
    #: login and never rewritten, so a role granted afterwards does not appear
    #: here until the user signs in again. Gate on ``permissions`` below.
    roles: list[str]
    #: The caller's effective permission codes, SORTED, resolved through the
    #: same version-keyed cache ``require_permission`` reads
    #: (``effective_permission_codes``). Discoverability for the UI
    #: (ui-standards §7) — **never** an authorization input: every route
    #: re-checks entitlement regardless of what the client was told, and no
    #: request path accepts one. api-standards §9j.
    #:
    #: Required, not defaulted: ``[]`` means "this person holds nothing" and
    #: drives the landing's no-access state, so it must never arrive by accident.
    permissions: list[str]
    idle_tier: str
    is_privileged: bool
    must_change_password: bool
    mfa_authenticated: bool
    mfa_setup_required: bool
    session: SessionSummary


class MfaEnrollResponse(BaseModel):
    secret: str
    otpauth_uri: str


class OkResponse(BaseModel):
    ok: bool = True


class RevokedResponse(BaseModel):
    revoked: int


class TempPasswordResponse(BaseModel):
    temporary_password: str
