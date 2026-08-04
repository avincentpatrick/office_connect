"""core/checklist/checks — the six auto-check types (build spec §5.3).

Pure: no DB. The governing rule under test throughout is *"a flag never blocks
alone"* — every check here can only ever say ``passed`` / ``flagged`` / ``skipped``,
and it is the ENGINE (not a check) that decides what blocks.
"""

import pytest

from office_connect.core.api.errors import APIError
from office_connect.core.checklist.checks import (
    FLAGGED,
    PASSED,
    SKIPPED,
    checks_outcome,
    run_auto_checks,
    validate_auto_checks,
)

TRIP = {
    "trip": {"depart": "2026-07-01", "return": "2026-07-03"},
    "legs": [
        {"seq": 1, "fare": "500.00", "leg_date": "2026-07-01"},
        {"seq": 2, "fare": "120.00", "leg_date": "2026-07-03"},
    ],
    "fare": ["500.00", "120.00"],
    "totals": {"transport": "620.00"},
    "config": {"receipts.cenrr_max": {"amount": "300.00"}},
    "today": "2026-08-03",
}


def one(spec, facts):
    results = run_auto_checks([spec], facts)
    assert len(results) == 1
    return results[0]


def with_item(facts, **item):
    base = {"evidence_count": 0, "evidence_pending": 0, "evidence_infected": 0}
    return {**facts, "item": {**base, **item}}


# --- file_present -----------------------------------------------------------


def test_file_present_flags_when_nothing_is_attached():
    result = one({"type": "file_present"}, with_item(TRIP))
    assert (result.outcome, result.reason) == (FLAGGED, "no_evidence")


def test_file_present_passes_with_a_clean_file():
    result = one({"type": "file_present"}, with_item(TRIP, evidence_count=1))
    assert (result.outcome, result.reason) == (PASSED, "evidence_present")


def test_a_pending_scan_passes_and_says_so():
    """Blocking a claimant because the virus scanner is behind would be a
    self-inflicted outage — the file is stored and counted."""
    result = one(
        {"type": "file_present"}, with_item(TRIP, evidence_count=1, evidence_pending=1)
    )
    assert result.outcome == PASSED
    assert result.reason == "evidence_scan_pending"
    assert "still being checked" in result.message


def test_an_infected_file_flags_because_the_bytes_are_quarantined():
    result = one({"type": "file_present"}, with_item(TRIP, evidence_infected=1))
    assert (result.outcome, result.reason) == (FLAGGED, "evidence_infected")


def test_file_present_skips_without_item_context():
    assert one({"type": "file_present"}, TRIP).outcome == SKIPPED


# --- amount_threshold (the one check the shipped catalog seeds) -------------

SEEDED = {
    "type": "amount_threshold",
    "field": "fare",
    "max_key": "receipts.cenrr_max",
    "on_exceed": "require_item:RER",
}


def test_amount_threshold_flags_the_leg_over_the_cenrr_limit():
    result = one(SEEDED, TRIP)
    assert (result.outcome, result.reason) == (FLAGGED, "amount_over_threshold")
    assert result.detail["over"] == ["500.00"]
    assert result.remedy == "require_item:RER"  # carried verbatim, never executed


def test_the_boundary_amount_is_not_over():
    facts = {**TRIP, "fare": ["300.00"]}
    assert one(SEEDED, facts).outcome == PASSED


def test_amount_threshold_accepts_a_scalar_as_well_as_a_list():
    assert one(SEEDED, {**TRIP, "fare": "450.00"}).outcome == FLAGGED
    assert one(SEEDED, {**TRIP, "fare": "50.00"}).outcome == PASSED


@pytest.mark.parametrize(
    "config",
    [
        {"receipts.cenrr_max": "300.00"},  # bare scalar
        {"receipts.cenrr_max": {"amount": "300.00"}},  # the shipped seed shape
    ],
)
def test_the_ceiling_unwraps_from_either_config_shape(config):
    assert one(SEEDED, {**TRIP, "config": config}).outcome == FLAGGED


def test_a_dotted_config_key_is_looked_up_flat_not_traversed():
    """Config keys contain dots (``receipts.cenrr_max``); a dotted resolver
    would hunt for a nested ``receipts`` object that does not exist."""
    nested = {"receipts": {"cenrr_max": {"amount": "300.00"}}}
    assert one(SEEDED, {**TRIP, "config": nested}).reason == "config_unavailable"


def test_a_missing_or_unreadable_ceiling_skips_rather_than_passing():
    assert one(SEEDED, {**TRIP, "config": {}}).reason == "config_unavailable"
    assert (
        one(SEEDED, {**TRIP, "config": {"receipts.cenrr_max": {"amount": "n/a"}}}).reason
        == "config_unavailable"
    )


def test_no_amount_yet_skips():
    assert one(SEEDED, {**TRIP, "fare": []}).reason == "no_amount"


# --- date_within_trip -------------------------------------------------------


def test_leg_dates_inside_the_trip_window_pass():
    assert one({"type": "date_within_trip"}, TRIP).outcome == PASSED


def test_a_leg_outside_the_trip_window_flags_and_names_it():
    facts = {
        **TRIP,
        "legs": [*TRIP["legs"], {"seq": 3, "leg_date": "2026-07-09"}],
    }
    result = one({"type": "date_within_trip"}, facts)
    assert (result.outcome, result.reason) == (FLAGGED, "date_outside_trip")
    assert "leg 3" in result.message


def test_receipt_dates_join_the_check_when_ocr_supplies_them():
    """Spec §5.3 says "receipt/leg dates" — leg dates work today, receipt dates
    widen the same check for free when OCR lands (R-9)."""
    facts = {**TRIP, "evidence_dates": ["2026-06-20"]}
    result = one({"type": "date_within_trip"}, facts)
    assert result.outcome == FLAGGED
    assert "receipt" in result.message


def test_date_within_trip_skips_before_the_trip_dates_are_set():
    assert one({"type": "date_within_trip"}, {**TRIP, "trip": {}}).reason == "no_trip"
    assert (
        one({"type": "date_within_trip"}, {**TRIP, "legs": []}).reason == "no_dates"
    )


# --- sum_matches ------------------------------------------------------------

SUM = {"type": "sum_matches", "of": "legs.fare", "vs": "totals.transport"}


def test_sum_matches_passes_when_the_parts_add_up():
    assert one(SUM, TRIP).outcome == PASSED


def test_sum_matches_flags_a_mismatch_and_reports_the_delta():
    result = one(SUM, {**TRIP, "totals": {"transport": "600.00"}})
    assert (result.outcome, result.reason) == (FLAGGED, "sum_mismatch")
    assert result.detail["delta"] == "20.00"


def test_tolerance_absorbs_a_small_difference():
    facts = {**TRIP, "totals": {"transport": "619.99"}}
    assert one({**SUM, "tolerance": "0.01"}, facts).outcome == PASSED
    assert one({**SUM, "tolerance": 0}, facts).outcome == FLAGGED


def test_sum_matches_skips_before_totals_are_computed():
    assert one(SUM, {**TRIP, "totals": {}}).reason == "no_total"


# --- keyword_absent (implemented; inert until OCR ships) --------------------

KEYWORDS = {"type": "keyword_absent", "keywords": ["business class", "first class"]}


def test_keyword_absent_skips_without_ocr_text_rather_than_passing():
    """The honest answer with no substrate is "not checked", never "clean" —
    which is why the type is registered rather than silently dropped."""
    assert one(KEYWORDS, TRIP).reason == "ocr_unavailable"


def test_keyword_absent_works_the_moment_ocr_text_exists():
    clean = one(KEYWORDS, {**TRIP, "ocr_text": "Economy fare, Manila to Cebu"})
    assert clean.outcome == PASSED
    dirty = one(KEYWORDS, {**TRIP, "ocr_text": "BUSINESS CLASS upgrade"})
    assert (dirty.outcome, dirty.detail["hits"]) == (FLAGGED, ["business class"])


# --- deadline_check (live since R-6-clock) ----------------------------------
#
# The substrate arrived with the liquidation clock: the module's fact builder
# now fills `deadlines` from the claim's linked cash advance (see
# test_reimb_checklist_facts.py). The skip branch below is no longer "not built
# yet" — it is the honest answer for a claim with NO cash advance, which has no
# deadline to be late against.

DEADLINE = {"type": "deadline_check", "key": "liquidation.deadline"}


def test_deadline_check_skips_when_the_claim_has_no_clock():
    assert one(DEADLINE, TRIP).reason == "deadline_clock_unavailable"


def test_deadline_check_works_once_a_deadline_is_supplied():
    facts = {**TRIP, "deadlines": {"liquidation.deadline": "2026-08-01"}}
    late = one(DEADLINE, facts)
    assert (late.outcome, late.detail["days_late"]) == (FLAGGED, 2)
    early = one(DEADLINE, {**facts, "today": "2026-07-20"})
    assert early.outcome == PASSED


# --- the unknown-type direction ---------------------------------------------


def test_an_unknown_check_type_skips_and_never_raises():
    """Asymmetric with an unknown RULE operator on purpose: a rule decides
    whether a document is required (a compliance fact), a check only decides
    what to tell the reviewer. Failing an unrecognized check closed would
    produce a flag nobody can action."""
    result = one({"type": "ocr_face_match"}, TRIP)
    assert (result.outcome, result.reason) == (SKIPPED, "unknown_check_type")


@pytest.mark.parametrize("checks", [None, {}, "file_present", 7])
def test_malformed_auto_checks_yield_nothing_rather_than_raising(checks):
    assert run_auto_checks(checks, TRIP) == ()


def test_a_non_object_entry_is_reported_not_dropped():
    assert run_auto_checks(["file_present"], TRIP)[0].reason == "malformed_check"


# --- roll-up ----------------------------------------------------------------


def test_checks_outcome_lets_any_flag_win():
    results = run_auto_checks([SEEDED, {"type": "date_within_trip"}], TRIP)
    assert checks_outcome(results) == FLAGGED
    assert checks_outcome(run_auto_checks([SUM], TRIP)) == PASSED
    assert checks_outcome(run_auto_checks([KEYWORDS], TRIP)) == SKIPPED
    assert checks_outcome([]) == SKIPPED


# --- validation (strict, authoring time) ------------------------------------


def test_validate_accepts_the_shipped_seed_and_every_spec_example():
    validate_auto_checks(None)
    validate_auto_checks([])
    validate_auto_checks([SEEDED, {"type": "file_present"}, SUM, KEYWORDS, DEADLINE])


@pytest.mark.parametrize(
    "checks",
    [
        {"type": "file_present"},  # not a list
        ["file_present"],
        [{"type": "ocr_face_match"}],
        [{"no_type": 1}],
        [{"type": "amount_threshold", "field": "fare"}],  # no max_key
        [{"type": "sum_matches", "of": "legs.fare"}],  # no vs
    ],
)
def test_validate_rejects_what_the_runner_merely_skips(checks):
    with pytest.raises(APIError) as exc:
        validate_auto_checks(checks)
    assert exc.value.status_code == 422
