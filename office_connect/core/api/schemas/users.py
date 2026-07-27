"""User provisioning endpoint models (api-standards §2).

Admin-only provisioning — no self-registration. Create mints a temporary password
(forced change on first login) returned once; no client-supplied password.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CreateUserRequest(BaseModel):
    staff_id: int
    # Optional override; defaults to the staff record's email when omitted.
    email: str | None = Field(default=None, max_length=320)


class CreatedUserResponse(BaseModel):
    user_id: int
    email: str
    # Shown ONCE for the admin to relay; never logged or audited.
    temporary_password: str = Field(...)


class UserSummary(BaseModel):
    id: int
    email: str
    is_active: bool
    is_break_glass: bool
    must_change_password: bool
    auth_source: str
    staff_id: int | None = None
    last_login_at: datetime | None = None
    created_at: datetime


class DeactivateResponse(BaseModel):
    user_id: int
    is_active: bool
    sessions_revoked: int
