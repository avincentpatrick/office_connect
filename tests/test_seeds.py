"""Increment 4 Group G — idempotent, environment-aware reference-data seeding."""

from sqlalchemy import select

from office_connect.core.models import (
    ActivityTag,
    ComplianceDeadline,
    Holiday,
    ObjectCode,
)
from office_connect.core.seeds import apply_all
from office_connect.core.seeds.base import SeedDataset


def test_environment_gate():
    local_only = SeedDataset("x", "o", "c", ("local",), object, (), ())
    assert local_only.loads_in("local") is True
    assert local_only.loads_in("production") is False
    everywhere = SeedDataset("y", "o", "c", ("all",), object, (), ())
    assert everywhere.loads_in("production") is True


async def test_seed_is_idempotent(app_session):
    await apply_all(app_session, app_env="local")
    await app_session.commit()
    # Second pass must upsert nothing new (no duplicates).
    second = await apply_all(app_session, app_env="local")
    await app_session.commit()
    for res in second:
        if "skipped" in res:
            continue
        assert res["inserted"] == 0, res
        assert res["updated"] == 0, res


async def test_reference_rows_present_after_seed(app_session):
    await apply_all(app_session, app_env="local")
    await app_session.commit()

    # A representative row from each reference dataset.
    tag = (
        await app_session.execute(
            select(ActivityTag).where(
                ActivityTag.taxonomy == "gad", ActivityTag.code == "attributed"
            )
        )
    ).scalar_one_or_none()
    assert tag is not None

    travel = (
        await app_session.execute(
            select(ObjectCode).where(ObjectCode.uacs_object_code == "5-02-01-010-00")
        )
    ).scalars().first()
    assert travel is not None

    holiday = (
        await app_session.execute(
            select(Holiday).where(Holiday.calendar_date.isnot(None), Holiday.name == "Independence Day")
        )
    ).scalars().first()
    assert holiday is not None

    csmr = (
        await app_session.execute(
            select(ComplianceDeadline).where(ComplianceDeadline.code == "csmr_to_arta")
        )
    ).scalars().first()
    assert csmr is not None and csmr.cadence == "annual"


async def test_reseed_restores_a_drifted_row(app_session):
    await apply_all(app_session, app_env="local", only={"compliance_deadlines"})
    await app_session.commit()

    row = (
        await app_session.execute(
            select(ComplianceDeadline).where(
                ComplianceDeadline.code == "csmr_to_arta",
                ComplianceDeadline.tenant_id.is_(None),
            )
        )
    ).scalar_one()
    canonical = row.name
    row.name = "DRIFTED VALUE"
    await app_session.commit()

    results = await apply_all(app_session, app_env="local", only={"compliance_deadlines"})
    await app_session.commit()
    refreshed = (
        await app_session.execute(
            select(ComplianceDeadline).where(
                ComplianceDeadline.code == "csmr_to_arta",
                ComplianceDeadline.tenant_id.is_(None),
            )
        )
    ).scalar_one()
    assert refreshed.name == canonical
    assert any(r.get("updated", 0) >= 1 for r in results)


async def test_reference_data_loads_in_production(app_session):
    """Reference data (public law/config) loads in every env — unlike synthetic
    fixtures, which bootstrap refuses in production."""
    results = await apply_all(app_session, app_env="production")
    await app_session.rollback()
    assert [r for r in results if "skipped" in r] == []
