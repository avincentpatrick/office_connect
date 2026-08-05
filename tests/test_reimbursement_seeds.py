"""R-1 config pack + catalogs — seeds load, are idempotent, and render with sources."""

from decimal import Decimal

from sqlalchemy import select

from office_connect.modules.reimbursement.models import (
    ReimbConfig,
    ReimbDteCluster,
    ReimbRegionCluster,
    ReimbReturnReasonCatalog,
)
from office_connect.modules.reimbursement.seeds import apply_reimbursement_seeds


async def test_seeds_load_and_are_idempotent(app_session):
    first = await apply_reimbursement_seeds(app_session)
    await app_session.commit()
    assert all(r["inserted"] >= 0 for r in first)

    # A second run changes nothing (idempotent upsert by natural key).
    second = await apply_reimbursement_seeds(app_session)
    await app_session.commit()
    assert all(r["inserted"] == 0 and r["updated"] == 0 for r in second), second


async def test_eo77_three_cluster_rates(app_session):
    await apply_reimbursement_seeds(app_session)
    await app_session.commit()
    rates = {
        c.cluster: c.daily_rate
        for c in (await app_session.execute(select(ReimbDteCluster))).scalars()
    }
    assert rates["I"] == Decimal("1500.00")
    assert rates["II"] == Decimal("1800.00")
    assert rates["III"] == Decimal("2200.00")


async def test_region_maps_to_cluster(app_session):
    await apply_reimbursement_seeds(app_session)
    await app_session.commit()
    ncr = (
        await app_session.execute(
            select(ReimbRegionCluster).where(ReimbRegionCluster.region_code == "13")
        )
    ).scalars().one()
    assert ncr.cluster == "III"  # NCR → ₱2,200
    # All 17 PH regions are mapped.
    count = len(
        (await app_session.execute(select(ReimbRegionCluster))).scalars().all()
    )
    assert count == 17


async def test_config_carries_legal_source(app_session):
    await apply_reimbursement_seeds(app_session)
    await app_session.commit()
    liq = (
        await app_session.execute(
            select(ReimbConfig).where(ReimbConfig.key == "liquidation.deadline")
        )
    ).scalars().one()
    assert liq.source == "COA Circular 97-002"
    assert liq.value["days"] == 30
    assert liq.value_display  # human-readable render present


async def test_return_reasons_seeded(app_session):
    await apply_reimbursement_seeds(app_session)
    await app_session.commit()
    reasons = (
        await app_session.execute(select(ReimbReturnReasonCatalog))
    ).scalars().all()
    assert len(reasons) >= 7
    # R-8 INVERTED this assertion. `promoted_check` used to be seeded loosely as
    # "this reason COULD be promoted" (three rows carried True); it now means
    # "this reason IS promoted", i.e. a warning every claimant sees at wizard
    # step 5. Nothing ships promoted, because a warning nobody authored is a
    # warning nobody can defend — the advisory's fail-safe direction is the
    # opposite of the packet gate's: when in doubt, do not warn.
    assert not any(r.promoted_check for r in reasons)
