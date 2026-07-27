"""Stage B (Phase 2) Increment 4 — CSS-IS directory ingestion.

Service-layer tests: idempotent upsert into core_org_units + core_staff (keyed by
code / employee_no), topological insert for the self-ref tree, tombstone restore,
atomic validation (a bad feed commits nothing), and audit-chain integrity.
"""

import uuid

import pytest
from sqlalchemy import select

from office_connect.core.audit import verify_chain
from office_connect.core.directory import DirectoryIngestError, ingest_directory
from office_connect.core.models import AuditLog, OrgUnit, Staff
from office_connect.core.soft_delete import soft_delete


def _tok() -> str:
    return uuid.uuid4().hex[:8]


def _feed(tok: str):
    root = f"OU-{tok}"
    div = f"{root}-DIV"
    sec = f"{root}-SEC"
    org_units = [
        {"code": root, "name": "Office", "kind": "office", "parent_code": None},
        {"code": div, "name": "Division", "kind": "division", "parent_code": root},
        {"code": sec, "name": "Section", "kind": "section", "parent_code": div},
    ]
    staff = [
        {
            "employee_no": f"E-{tok}-1",
            "given_name": "Maria",
            "surname": "Santos",
            "email": f"maria-{tok}@doh.gov",
            "position_title": "Chief",
            "division_code": div,
            "section_code": sec,
        },
        {
            "employee_no": f"E-{tok}-2",
            "given_name": "Jose",
            "surname": "Cruz",
            "division_code": div,
        },
    ]
    return org_units, staff, root, div, sec


async def _org(session, code):
    return (
        await session.execute(select(OrgUnit).where(OrgUnit.code == code))
    ).scalar_one_or_none()


async def _staff(session, emp):
    return (
        await session.execute(select(Staff).where(Staff.employee_no == emp))
    ).scalar_one_or_none()


async def test_creates_tree_and_staff(app_session):
    tok = _tok()
    org_units, staff, root, div, sec = _feed(tok)
    result = await ingest_directory(app_session, org_units=org_units, staff=staff)
    await app_session.commit()

    assert set(result.org_units_created) == {root, div, sec}
    assert set(result.staff_created) == {f"E-{tok}-1", f"E-{tok}-2"}

    division = await _org(app_session, div)
    section = await _org(app_session, sec)
    assert section.parent_org_unit_id == division.id
    s1 = await _staff(app_session, f"E-{tok}-1")
    assert s1.division_id == division.id and s1.section_id == section.id
    assert s1.full_name == "Maria Santos"  # derived when blank


async def test_idempotent(app_session):
    tok = _tok()
    org_units, staff, *_ = _feed(tok)
    await ingest_directory(app_session, org_units=org_units, staff=staff)
    await app_session.commit()
    again = await ingest_directory(app_session, org_units=org_units, staff=staff)
    await app_session.commit()
    assert again.org_units_created == [] and again.staff_created == []
    assert set(again.org_units_updated) and set(again.staff_updated)


async def test_topological_arbitrary_order(app_session):
    tok = _tok()
    root = f"OU-{tok}"
    div = f"{root}-DIV"
    # Child listed BEFORE its parent — must still resolve.
    org_units = [
        {"code": div, "name": "Division", "kind": "division", "parent_code": root},
        {"code": root, "name": "Office", "kind": "office", "parent_code": None},
    ]
    await ingest_directory(app_session, org_units=org_units, staff=[])
    await app_session.commit()
    assert (await _org(app_session, div)).parent_org_unit_id == (
        await _org(app_session, root)
    ).id


async def test_restores_soft_deleted_staff(app_session):
    tok = _tok()
    org_units, staff, *_ = _feed(tok)
    await ingest_directory(app_session, org_units=org_units, staff=staff)
    await app_session.commit()

    emp = f"E-{tok}-1"
    row = await _staff(app_session, emp)
    soft_delete(row)
    await app_session.commit()
    assert await _staff(app_session, emp) is None  # filtered out while tombstoned

    result = await ingest_directory(app_session, org_units=org_units, staff=staff)
    await app_session.commit()
    assert emp in result.staff_restored
    assert await _staff(app_session, emp) is not None  # back to live


async def test_rejects_unknown_parent_atomically(app_session):
    tok = _tok()
    code = f"OU-{tok}-ORPHAN"
    org_units = [
        {"code": code, "name": "Orphan", "kind": "division", "parent_code": "NOPE"}
    ]
    with pytest.raises(DirectoryIngestError):
        await ingest_directory(app_session, org_units=org_units, staff=[])
    await app_session.rollback()
    assert await _org(app_session, code) is None  # nothing committed


async def test_rejects_bad_division_kind_atomically(app_session):
    tok = _tok()
    root = f"OU-{tok}"
    org_units = [
        {"code": root, "name": "Office", "kind": "office", "parent_code": None}
    ]
    staff = [
        {
            "employee_no": f"E-{tok}-x",
            "given_name": "A",
            "surname": "B",
            # points at an OFFICE where a DIVISION is required
            "division_code": root,
        }
    ]
    with pytest.raises(DirectoryIngestError):
        await ingest_directory(app_session, org_units=org_units, staff=staff)
    await app_session.rollback()
    assert await _org(app_session, root) is None  # org unit not flushed either


async def test_audited_and_chain_verifies(app_session, owner_session):
    tok = _tok()
    org_units, staff, root, *_ = _feed(tok)
    await ingest_directory(app_session, org_units=org_units, staff=staff)
    await app_session.commit()

    unit = await _org(app_session, root)
    inserts = (
        await owner_session.execute(
            select(AuditLog).where(
                AuditLog.table_name == "core_org_units",
                AuditLog.row_pk == unit.id,
                AuditLog.action == "insert",
            )
        )
    ).scalars().all()
    assert inserts  # the ingest write is on the hash chain
    rows = (
        (await owner_session.execute(select(AuditLog).order_by(AuditLog.id)))
        .scalars()
        .all()
    )
    assert verify_chain(rows) is None


async def test_prune_empty_feed_guarded(app_session):
    with pytest.raises(DirectoryIngestError):
        await ingest_directory(
            app_session, org_units=[], staff=[], deactivate_absent=True
        )
    await app_session.rollback()


async def test_default_never_prunes(app_session):
    tok = _tok()
    org_units, staff, *_ = _feed(tok)
    await ingest_directory(app_session, org_units=org_units, staff=staff)
    await app_session.commit()

    # A later partial feed omitting E-...-2 must NOT deactivate it (leave-alone).
    partial = [staff[0]]
    await ingest_directory(app_session, org_units=org_units, staff=partial)
    await app_session.commit()
    assert await _staff(app_session, f"E-{tok}-2") is not None
