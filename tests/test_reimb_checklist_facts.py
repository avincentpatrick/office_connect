"""R-3 — the fact contract the catalog's JSONB rules are written against.

These keys are referenced BY NAME from seeded data (``{"field": "totals.other"}``),
so this file is a contract test, not an implementation test: renaming a key here
is a catalog migration.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from office_connect.core.checklist import required_rule_applies
from office_connect.core.soft_delete import soft_delete
from office_connect.modules.reimbursement.models import (
    ReimbConfig,
    ReimbItineraryLeg,
)
from office_connect.modules.reimbursement.services.checklist_facts import (
    FACTS_VERSION,
    build_claim_facts,
)
from tests.reimb_lifecycle_helpers import standard_cast


async def test_the_published_keys_are_all_present(make_user, seed_rbac, app_session):
    cast = await standard_cast(app_session, make_user, packet=False)
    facts = await build_claim_facts(app_session, claim=cast.claim)

    assert set(facts) >= {
        "kind",
        "is_jo_cos",
        "fund_source",
        "is_within_50km",
        "overnight_stay",
        "transport_modes",
        "fare",
        "legs",
        "leg_count",
        "trip",
        "totals",
        "config",
        "deadlines",
        "evidence_dates",
        "ocr_text",
        "today",
        "facts_version",
    }
    assert facts["facts_version"] == FACTS_VERSION
    assert facts["trip"] == {
        "depart": "2026-07-01",
        "return": "2026-07-03",
        "days": 3,
    }


async def test_transport_modes_are_sorted_unique_and_live_only(
    make_user, seed_rbac, app_session
):
    """A deleted taxi leg must stop RER-46 applying — the soft-delete filter is
    what makes that automatic."""
    from tests.reimbursement_helpers import make_leg

    cast = await standard_cast(app_session, make_user, packet=False)
    taxi = await make_leg(
        app_session,
        claim_id=cast.claim.id,
        seq=3,
        leg_date=date(2026, 7, 2),
        transport_mode="taxi",
        fare="120.00",
    )
    facts = await build_claim_facts(app_session, claim=cast.claim)
    assert facts["transport_modes"] == ["bus", "taxi"]  # sorted, de-duped
    rule = {"if": {"field": "transport_modes", "contains": "taxi"}}
    assert required_rule_applies(rule, facts) is True

    soft_delete(taxi, actor_id=cast.owner.id)
    await app_session.flush()
    facts = await build_claim_facts(app_session, claim=cast.claim)
    assert facts["transport_modes"] == ["bus"]
    assert required_rule_applies(rule, facts) is False


async def test_other_comes_from_the_column_not_the_cleared_snapshot(
    make_user, seed_rbac, app_session
):
    """``drafts.py`` clears ``claim.totals`` on every compute-input edit, so
    reading "other" out of the snapshot would make LOD-01 silently stop being
    required mid-edit. Since migration 0016 the COLUMN is the truth."""
    cast = await standard_cast(app_session, make_user, packet=False)
    cast.claim.other_total = Decimal("250.00")
    cast.claim.totals = {}  # exactly what a compute-input edit leaves behind
    await app_session.flush()

    facts = await build_claim_facts(app_session, claim=cast.claim)
    assert facts["totals"]["other"] == "250.00"
    assert required_rule_applies({"if": {"field": "totals.other", "gt": 0}}, facts)


async def test_money_crosses_as_two_decimal_strings(
    make_user, seed_rbac, app_session
):
    cast = await standard_cast(app_session, make_user, packet=False)
    facts = await build_claim_facts(app_session, claim=cast.claim)
    assert facts["fare"] == ["500.00", "500.00"]
    assert facts["totals"]["other"] == "0.00"


async def test_config_is_effective_dated_and_keyed_verbatim(
    make_user, seed_rbac, app_session
):
    """Keys keep their dots (``receipts.cenrr_max``) — the auto-check looks them
    up FLAT for exactly this reason."""
    cast = await standard_cast(app_session, make_user, packet=False)
    facts = await build_claim_facts(app_session, claim=cast.claim)
    assert facts["config"]["receipts.cenrr_max"] == {"amount": "300.00"}

    # A superseded row wins once its effective date has arrived…
    app_session.add(
        ReimbConfig(
            key="receipts.cenrr_max",
            value={"amount": "500.00"},
            effective_from=date(2026, 1, 1),
            source="test",
        )
    )
    # …and a future-dated one is ignored until then.
    app_session.add(
        ReimbConfig(
            key="receipts.cenrr_max",
            value={"amount": "999.00"},
            effective_from=date(2099, 1, 1),
            source="test",
        )
    )
    await app_session.flush()
    facts = await build_claim_facts(app_session, claim=cast.claim)
    assert facts["config"]["receipts.cenrr_max"] == {"amount": "500.00"}
    await app_session.rollback()


async def test_an_empty_claim_builds_facts_without_raising(
    make_user, seed_rbac, app_session
):
    """The Documents step must render for a barely-started draft — every rule
    has to evaluate against a claim with no dates and no legs."""
    from tests.reimbursement_helpers import make_claim, make_staff

    staff = await make_staff(app_session)
    claim = await make_claim(app_session, claimant_id=staff.id)
    await app_session.execute(
        select(ReimbItineraryLeg).where(ReimbItineraryLeg.claim_id == claim.id)
    )

    facts = await build_claim_facts(app_session, claim=claim)
    assert facts["trip"] == {"depart": None, "return": None, "days": None}
    assert facts["transport_modes"] == []
    assert facts["leg_count"] == 0
    for rule in (
        {"always": True},
        {"if": {"field": "is_jo_cos", "eq": True}},
        {"if": {"field": "transport_modes", "contains": "taxi"}},
        {"if": {"field": "totals.other", "gt": 0}},
    ):
        required_rule_applies(rule, facts)  # must not raise
