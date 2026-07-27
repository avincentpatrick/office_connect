"""Directory (staff + org units) endpoint models (api-standards §2)."""

from __future__ import annotations

from pydantic import BaseModel


class IngestSummary(BaseModel):
    org_units_created: list[str]
    org_units_updated: list[str]
    org_units_restored: list[str]
    staff_created: list[str]
    staff_updated: list[str]
    staff_restored: list[str]
    staff_deactivated: list[str]


class StaffSummary(BaseModel):
    id: int
    employee_no: str
    given_name: str
    middle_name: str | None = None
    surname: str
    full_name: str
    email: str | None = None
    position_title: str | None = None
    employment_status: str | None = None
    division_id: int | None = None
    section_id: int | None = None


class OrgUnitSummary(BaseModel):
    id: int
    code: str
    name: str
    kind: str
    parent_org_unit_id: int | None = None
    sort_order: int
    is_active: bool
