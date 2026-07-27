"""Directory endpoints (Stage B / Increment 4).

``POST /directory/import`` lands a CSS-IS-shaped CSV feed (org units + staff) into
the directory via the pure ``core.directory.ingest`` service — CSV parsing lives
here (transport), the upsert logic stays format-agnostic. Read endpoints back the
provisioning UI's person/org pickers. All gated on ``staff.*`` / ``orgunit.*``.
"""

from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.api.errors import APIError
from office_connect.core.api.schemas.directory import (
    IngestSummary,
    OrgUnitSummary,
    StaffSummary,
)
from office_connect.core.auth.dependencies import require_permission
from office_connect.core.auth.principal import Principal
from office_connect.core.db import get_session
from office_connect.core.directory import DirectoryIngestError, ingest_directory
from office_connect.core.models import OrgUnit, Staff

router = APIRouter()


async def _parse_csv(file: UploadFile | None) -> list[dict]:
    if file is None:
        return []
    raw = await file.read()
    text = raw.decode("utf-8-sig")  # tolerate a UTF-8 BOM from spreadsheet exports
    return [dict(row) for row in csv.DictReader(io.StringIO(text))]


def _staff_summary(s: Staff) -> StaffSummary:
    return StaffSummary(
        id=s.id,
        employee_no=s.employee_no,
        given_name=s.given_name,
        middle_name=s.middle_name,
        surname=s.surname,
        full_name=s.full_name,
        email=s.email,
        position_title=s.position_title,
        employment_status=s.employment_status,
        division_id=s.division_id,
        section_id=s.section_id,
    )


@router.post("/directory/import", response_model=IngestSummary)
async def import_directory(
    request: Request,
    org_units_file: UploadFile | None = File(None),
    staff_file: UploadFile | None = File(None),
    principal: Principal = Depends(require_permission("staff.import")),
    session: AsyncSession = Depends(get_session),
):
    org_units = await _parse_csv(org_units_file)
    staff = await _parse_csv(staff_file)
    if not org_units and not staff:
        raise APIError(
            422,
            "validation_error",
            "Provide at least one of org_units_file / staff_file.",
        )
    try:
        result = await ingest_directory(
            session,
            org_units=org_units,
            staff=staff,
            actor_id=principal.user_id,
            request_id=getattr(request.state, "request_id", None),
        )
    except DirectoryIngestError as exc:
        raise APIError(
            422,
            "directory_ingest_failed",
            "The directory feed failed validation.",
            details=exc.errors,
        ) from exc
    await session.commit()
    return IngestSummary(
        org_units_created=result.org_units_created,
        org_units_updated=result.org_units_updated,
        org_units_restored=result.org_units_restored,
        staff_created=result.staff_created,
        staff_updated=result.staff_updated,
        staff_restored=result.staff_restored,
        staff_deactivated=result.staff_deactivated,
    )


@router.get("/directory/staff", response_model=list[StaffSummary])
async def list_staff(
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
    _: Principal = Depends(require_permission("staff.read")),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(Staff).order_by(Staff.surname, Staff.id)
    if q:
        stmt = stmt.where(
            or_(Staff.surname.ilike(f"%{q}%"), Staff.employee_no.ilike(f"%{q}%"))
        )
    stmt = stmt.limit(min(limit, 200)).offset(max(offset, 0))
    rows = (await session.execute(stmt)).scalars().all()
    return [_staff_summary(s) for s in rows]


@router.get("/directory/staff/{staff_id}", response_model=StaffSummary)
async def get_staff(
    staff_id: int,
    _: Principal = Depends(require_permission("staff.read")),
    session: AsyncSession = Depends(get_session),
):
    row = (
        await session.execute(select(Staff).where(Staff.id == staff_id))
    ).scalar_one_or_none()
    if row is None:
        raise APIError(404, "not_found", "Staff record not found.")
    return _staff_summary(row)


@router.get("/directory/org-units", response_model=list[OrgUnitSummary])
async def list_org_units(
    _: Principal = Depends(require_permission("orgunit.read")),
    session: AsyncSession = Depends(get_session),
):
    rows = (
        await session.execute(select(OrgUnit).order_by(OrgUnit.sort_order, OrgUnit.code))
    ).scalars().all()
    return [
        OrgUnitSummary(
            id=ou.id,
            code=ou.code,
            name=ou.name,
            kind=ou.kind,
            parent_org_unit_id=ou.parent_org_unit_id,
            sort_order=ou.sort_order,
            is_active=ou.is_active,
        )
        for ou in rows
    ]
