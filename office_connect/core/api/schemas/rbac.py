"""RBAC admin endpoint request/response models (Stage B / Increment 3)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class GrantRoleRequest(BaseModel):
    role_id: int
    # NULL = global grant; set = scoped ("role OF org-unit X").
    org_unit_id: int | None = None
    # Delegation / OIC window (UTC). Absent = permanent grant.
    valid_from: datetime | None = None
    valid_to: datetime | None = None


class UserRoleSummary(BaseModel):
    id: int
    user_id: int
    role_id: int
    org_unit_id: int | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None


class RoleSummary(BaseModel):
    id: int
    code: str
    name: str
    is_system: bool
    is_active: bool


class PermissionSummary(BaseModel):
    id: int
    code: str
    name: str
    category: str | None = None
