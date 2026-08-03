"""core/checklist/engine — reconciliation + the completeness rule.

Pure: no DB. These tests pin the four behaviours the whole increment rests on —
idempotent re-materialization, evidence preservation, "a flag never blocks
alone", and "a system-generated document is never a precondition of submit".
"""

import pytest

from office_connect.core.checklist import (
    BLOCKING_EVIDENCE,
    CREATE,
    ITEM_STATUSES,
    KEEP,
    MAKE_DORMANT,
    RESTORE,
    SATISFIED_STATUSES,
    CatalogSpec,
    ItemState,
    packet_status,
    plan_checklist,
)

FACTS = {
    "is_jo_cos": True,
    "transport_modes": ["bus", "taxi"],
    "totals": {"other": "250.00", "transport": "620.00"},
    "fare": ["500.00", "120.00"],
    "config": {"receipts.cenrr_max": {"amount": "300.00"}},
    "legs": [{"seq": 1, "fare": "500.00", "leg_date": "2026-07-01"}],
    "trip": {"depart": "2026-07-01", "return": "2026-07-03"},
    "today": "2026-08-03",
}


def spec(catalog_id, code, *, evidence="upload", rule=None, checks=None, sort=0):
    return CatalogSpec(
        catalog_id=catalog_id,
        code=code,
        label=f"{code} label",
        group="authority",
        evidence=evidence,
        required_rule=rule if rule is not None else {"always": True},
        auto_checks=checks or [],
        sort=sort,
    )


# The shipped catalog, in miniature: two always-on uploads, one conditional
# upload, one generated doc, one wet-sign.
TO_01 = spec(1, "TO-01", sort=1)
JO_01 = spec(2, "JO-01", rule={"if": {"field": "is_jo_cos", "eq": True}}, sort=2)
IOT_45 = spec(3, "IOT-45", evidence="generated_doc", sort=3)
CTC_47 = spec(4, "CTC-47", evidence="external_wet_sign", sort=4)
RER_46 = spec(
    5,
    "RER-46",
    rule={"if": {"field": "transport_modes", "contains": "taxi"}},
    checks=[
        {
            "type": "amount_threshold",
            "field": "fare",
            "max_key": "receipts.cenrr_max",
            "on_exceed": "require_item:RER",
        }
    ],
    sort=5,
)
CATALOG = [TO_01, JO_01, IOT_45, CTC_47, RER_46]


def by_code(plan):
    return {item.catalog.code: item for item in plan}


# --- planning ---------------------------------------------------------------


def test_a_fresh_subject_plans_every_applicable_row_as_a_create():
    plan = plan_checklist(catalog=CATALOG, existing=[], facts=FACTS)
    assert {item.catalog.code for item in plan} == {
        "TO-01",
        "JO-01",
        "IOT-45",
        "CTC-47",
        "RER-46",
    }
    assert {item.action for item in plan} == {CREATE}
    assert all(item.item_id is None for item in plan)


def test_a_rule_that_does_not_apply_produces_no_row_at_all():
    plan = plan_checklist(
        catalog=CATALOG, existing=[], facts={**FACTS, "is_jo_cos": False}
    )
    assert "JO-01" not in by_code(plan)


def test_the_plan_is_ordered_by_sort_then_code():
    plan = plan_checklist(catalog=list(reversed(CATALOG)), existing=[], facts=FACTS)
    assert [item.catalog.code for item in plan] == [
        "TO-01",
        "JO-01",
        "IOT-45",
        "CTC-47",
        "RER-46",
    ]


def test_re_planning_unchanged_inputs_is_a_no_op():
    """The idempotency contract: a consumer that writes only on a real change
    performs zero work on a second call."""
    existing = [
        ItemState(item_id=10 + s.catalog_id, catalog_id=s.catalog_id) for s in CATALOG
    ]
    plan = plan_checklist(catalog=CATALOG, existing=existing, facts=FACTS)
    assert {item.action for item in plan} == {KEEP}
    again = plan_checklist(catalog=CATALOG, existing=existing, facts=FACTS)
    assert plan == again


def test_an_empty_item_that_stops_applying_goes_dormant():
    existing = [ItemState(item_id=12, catalog_id=JO_01.catalog_id)]
    plan = by_code(
        plan_checklist(
            catalog=CATALOG, existing=existing, facts={**FACTS, "is_jo_cos": False}
        )
    )
    assert plan["JO-01"].action == MAKE_DORMANT
    assert plan["JO-01"].required is False


def test_an_item_that_stops_applying_but_holds_evidence_is_never_removed():
    """Severing a subject-to-document link is a records-management act, not a
    projection refresh — so the row stays live, merely not-required."""
    existing = [ItemState(item_id=12, catalog_id=JO_01.catalog_id, evidence_count=1)]
    item = by_code(
        plan_checklist(
            catalog=CATALOG, existing=existing, facts={**FACTS, "is_jo_cos": False}
        )
    )["JO-01"]
    assert item.action == KEEP
    assert (item.required, item.evidence_state) == (False, "attached")


@pytest.mark.parametrize(
    "state", [{"waived": True}, {"generated": True}, {"evidence_count": 2}]
)
def test_anything_holding_work_survives_becoming_inapplicable(state):
    existing = [ItemState(item_id=12, catalog_id=JO_01.catalog_id, **state)]
    plan = by_code(
        plan_checklist(
            catalog=CATALOG, existing=existing, facts={**FACTS, "is_jo_cos": False}
        )
    )
    assert plan["JO-01"].action == KEEP


def test_a_dormant_row_is_restored_with_its_identity_intact():
    existing = [ItemState(item_id=12, catalog_id=JO_01.catalog_id, dormant=True)]
    item = by_code(plan_checklist(catalog=CATALOG, existing=existing, facts=FACTS))[
        "JO-01"
    ]
    assert (item.action, item.item_id) == (RESTORE, 12)


def test_a_dormant_row_that_still_does_not_apply_is_left_alone():
    existing = [ItemState(item_id=12, catalog_id=JO_01.catalog_id, dormant=True)]
    plan = plan_checklist(
        catalog=CATALOG, existing=existing, facts={**FACTS, "is_jo_cos": False}
    )
    assert "JO-01" not in by_code(plan)


# --- derived status ---------------------------------------------------------


def test_status_derives_from_evidence_then_checks():
    existing = [ItemState(item_id=1, catalog_id=TO_01.catalog_id, evidence_count=1)]
    plan = by_code(plan_checklist(catalog=CATALOG, existing=existing, facts=FACTS))
    # No auto_checks on TO-01 → plain "attached".
    assert plan["TO-01"].derived_status == "attached"
    # RER-46 has a flagging amount_threshold but no file → still missing.
    assert plan["RER-46"].derived_status == "missing"


def test_an_attached_item_whose_check_flags_reads_auto_flagged_and_still_counts():
    """The single status column expresses "attached AND flagged" exactly, and
    the gate does not care — it reads the evidence underneath (spec §5.3:
    "a flag never blocks alone")."""
    existing = [ItemState(item_id=5, catalog_id=RER_46.catalog_id, evidence_count=1)]
    item = by_code(plan_checklist(catalog=CATALOG, existing=existing, facts=FACTS))[
        "RER-46"
    ]
    assert item.derived_status == "auto_flagged"
    assert item.derived_status in SATISFIED_STATUSES
    assert item.blocking is False
    assert [check.reason for check in item.flags] == ["amount_over_threshold"]


def test_an_attached_item_whose_checks_pass_reads_auto_passed():
    existing = [ItemState(item_id=5, catalog_id=RER_46.catalog_id, evidence_count=1)]
    item = by_code(
        plan_checklist(
            catalog=CATALOG, existing=existing, facts={**FACTS, "fare": ["100.00"]}
        )
    )["RER-46"]
    assert item.derived_status == "auto_passed"


def test_a_human_waiver_outranks_every_machine_verdict():
    existing = [
        ItemState(item_id=5, catalog_id=RER_46.catalog_id, evidence_count=1, waived=True)
    ]
    item = by_code(plan_checklist(catalog=CATALOG, existing=existing, facts=FACTS))[
        "RER-46"
    ]
    assert (item.derived_status, item.evidence_state) == ("waived", "waived")


def test_a_data_only_item_is_satisfied_by_the_data_itself():
    """Nothing to attach, so nothing can be absent. It can still flag, which is
    how a data problem reaches the reviewer."""
    data_only = spec(9, "DAT-01", evidence="data_only", checks=[{"type": "sum_matches", "of": "legs.fare", "vs": "totals.transport"}])
    item = by_code(plan_checklist(catalog=[data_only], existing=[], facts=FACTS))["DAT-01"]
    assert item.evidence_state == "attached"
    assert item.blocking is False
    bad = by_code(
        plan_checklist(
            catalog=[data_only],
            existing=[],
            facts={**FACTS, "totals": {"transport": "1.00"}},
        )
    )["DAT-01"]
    assert bad.derived_status == "auto_flagged"
    assert bad.blocking is False


def test_every_derived_status_is_in_the_published_vocabulary():
    existing = [
        ItemState(item_id=1, catalog_id=TO_01.catalog_id, evidence_count=1),
        ItemState(item_id=3, catalog_id=IOT_45.catalog_id, generated=True),
        ItemState(item_id=5, catalog_id=RER_46.catalog_id, waived=True),
    ]
    plan = plan_checklist(catalog=CATALOG, existing=existing, facts=FACTS)
    assert {item.derived_status for item in plan} <= set(ITEM_STATUSES)


# --- the completeness rule --------------------------------------------------


def test_a_generated_document_is_never_a_precondition_of_submit():
    """A system-produced artifact cannot gate entry to the workflow that
    produces it. Without this the three always-on generated_doc rows in the
    shipped catalog would make every claim permanently unsubmittable."""
    status = packet_status(plan_checklist(catalog=CATALOG, existing=[], facts=FACTS))
    assert "IOT-45" not in {item.code for item in status.blocking}
    assert "generated_doc" not in BLOCKING_EVIDENCE


def test_the_blocking_list_names_exactly_the_human_evidence_that_is_absent():
    status = packet_status(plan_checklist(catalog=CATALOG, existing=[], facts=FACTS))
    assert {item.code for item in status.blocking} == {
        "TO-01",
        "JO-01",
        "CTC-47",
        "RER-46",
    }
    assert status.complete is False
    assert (status.required_done, status.required_total) == (0, 4)


def test_the_progress_line_counts_only_items_the_claimant_can_act_on():
    """"2 of 5 done" with three rows nobody can touch is a progress bar that
    never finishes."""
    existing = [
        ItemState(item_id=1, catalog_id=TO_01.catalog_id, evidence_count=1),
        ItemState(item_id=2, catalog_id=JO_01.catalog_id, evidence_count=1),
    ]
    status = packet_status(
        plan_checklist(catalog=CATALOG, existing=existing, facts=FACTS)
    )
    assert (status.required_done, status.required_total) == (2, 4)


def test_a_packet_is_complete_once_every_blocking_item_holds_evidence():
    existing = [
        ItemState(item_id=n, catalog_id=n, evidence_count=1) for n in (1, 2, 4, 5)
    ]
    status = packet_status(
        plan_checklist(catalog=CATALOG, existing=existing, facts=FACTS)
    )
    assert status.complete is True
    assert status.blocking == ()
    # …and the flag from RER-46's over-limit fare is still reported.
    assert [check.reason for _, check in status.flags] == ["amount_over_threshold"]


def test_flags_never_reduce_completeness():
    existing = [
        ItemState(item_id=n, catalog_id=n, evidence_count=1) for n in (1, 2, 4, 5)
    ]
    flagging = packet_status(
        plan_checklist(catalog=CATALOG, existing=existing, facts=FACTS)
    )
    clean = packet_status(
        plan_checklist(
            catalog=CATALOG, existing=existing, facts={**FACTS, "fare": ["10.00"]}
        )
    )
    assert flagging.complete == clean.complete is True
    assert len(flagging.flags) == 1 and clean.flags == ()


def test_an_unparseable_rule_is_reported_without_blocking():
    """Fail-open plus a visible flag: with no waiver path, blocking on a rule we
    could not read would strand the claim forever (spec §9.1 principle 4)."""
    broken = spec(9, "BAD-01", rule={"iff": True})
    status = packet_status(plan_checklist(catalog=[broken], existing=[], facts=FACTS))
    assert status.unparseable == (9,)
    assert status.blocking == ()


def test_an_empty_packet_is_complete():
    status = packet_status(())
    assert (status.complete, status.required_total) == (True, 0)
