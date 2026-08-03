"""core/checklist/grammar — the ``required_rule`` operator set (build spec §5.3).

Pure: no DB, no fixtures. Every shape the shipped catalog seeds appears here
verbatim, so a change to the grammar that breaks a seeded row fails loudly.
"""

import pytest

from office_connect.core.api.errors import APIError
from office_connect.core.checklist import grammar
from office_connect.core.checklist.grammar import (
    MISSING,
    evaluate_required_rule,
    required_rule_applies,
    resolve_field,
    validate_required_rule,
)

FACTS = {
    "is_jo_cos": True,
    "fund_source": None,
    "transport_modes": ["bus", "taxi"],
    "totals": {"other": "250.00", "transport": "620.00"},
    "legs": [
        {"seq": 1, "fare": "500.00"},
        {"seq": 2, "fare": "120.00"},
        {"seq": 3},  # no fare — projection must skip, not explode
    ],
}


# --- the four seeded rule shapes -------------------------------------------


def test_always_true_requires_and_always_false_does_not():
    assert evaluate_required_rule({"always": True}, FACTS).required is True
    assert evaluate_required_rule({"always": True}, FACTS).reason == "always"
    assert evaluate_required_rule({"always": False}, FACTS).required is False


def test_if_eq_matches_a_boolean_fact():
    """JO-01: Head-of-Office certification for a JO/COS claimant."""
    rule = {"if": {"field": "is_jo_cos", "eq": True}}
    assert required_rule_applies(rule, FACTS) is True
    assert required_rule_applies(rule, {**FACTS, "is_jo_cos": False}) is False
    assert evaluate_required_rule(rule, {**FACTS, "is_jo_cos": False}).reason == (
        "condition_unmet"
    )


def test_if_contains_matches_membership_and_substrings():
    """RER-46: a taxi leg spawns the reimbursement-expense-receipt item."""
    rule = {"if": {"field": "transport_modes", "contains": "taxi"}}
    assert required_rule_applies(rule, FACTS) is True
    assert required_rule_applies(rule, {**FACTS, "transport_modes": ["bus"]}) is False
    assert required_rule_applies(rule, {**FACTS, "transport_modes": []}) is False
    # A string fact is a substring test, not a membership one.
    assert required_rule_applies(
        {"if": {"field": "purpose", "contains": "training"}},
        {"purpose": "Regional training workshop"},
    )


def test_if_gt_coerces_the_two_decimal_money_string():
    """LOD-01. Money crosses as a 2-dp STRING (core/money.money_str) — without
    Decimal coercion this rule would silently never fire, which is the whole
    reason the comparator exists."""
    rule = {"if": {"field": "totals.other", "gt": 0}}
    assert required_rule_applies(rule, FACTS) is True
    assert required_rule_applies(rule, {"totals": {"other": "0.00"}}) is False
    assert required_rule_applies(rule, {"totals": {"other": "0.01"}}) is True


def test_gt_is_false_when_either_side_is_not_numeric():
    assert required_rule_applies({"if": {"field": "purpose", "gt": 0}}, FACTS) is False
    assert required_rule_applies({"if": {"field": "totals.other", "gt": "x"}}, FACTS) is False


def test_true_is_not_the_number_one():
    """A boolean must not sneak through the numeric path of ``eq``."""
    assert required_rule_applies({"if": {"field": "is_jo_cos", "eq": 1}}, FACTS) is False


# --- junctions --------------------------------------------------------------


def test_any_and_all_combine_branches():
    taxi = {"if": {"field": "transport_modes", "contains": "taxi"}}
    plane = {"if": {"field": "transport_modes", "contains": "plane"}}
    assert required_rule_applies({"any": [taxi, plane]}, FACTS) is True
    assert required_rule_applies({"all": [taxi, plane]}, FACTS) is False
    assert required_rule_applies({"all": [taxi, {"always": True}]}, FACTS) is True


def test_junctions_nest():
    rule = {
        "all": [
            {"always": True},
            {"any": [{"if": {"field": "is_jo_cos", "eq": True}}, {"always": False}]},
        ]
    }
    assert required_rule_applies(rule, FACTS) is True
    assert required_rule_applies(rule, {**FACTS, "is_jo_cos": False}) is False


def test_empty_junctions_follow_boolean_algebra():
    assert required_rule_applies({"any": []}, FACTS) is False  # vacuously false
    assert required_rule_applies({"all": []}, FACTS) is True  # vacuously true


def test_one_unreadable_branch_poisons_the_junction():
    """We cannot honestly say a junction was satisfied when part of it was
    unreadable — so it reports unparseable rather than guessing."""
    outcome = evaluate_required_rule({"any": [{"always": True}, {"nope": 1}]}, FACTS)
    assert outcome.unparseable is True


def test_recursion_is_bounded():
    rule = {"always": True}
    for _ in range(grammar.MAX_RULE_DEPTH + 2):
        rule = {"all": [rule]}
    assert evaluate_required_rule(rule, FACTS).unparseable is True


# --- the failure direction --------------------------------------------------


@pytest.mark.parametrize(
    "rule",
    [
        None,
        [],
        "always",
        {"iff": {"field": "is_jo_cos", "eq": True}},  # unknown operator
        {"always": True, "if": {"field": "x", "eq": 1}},  # two operators in one node
        {"if": {"field": "is_jo_cos"}},  # no comparator
        {"if": {"field": "is_jo_cos", "eq": True, "gt": 1}},  # two comparators
        {"if": {"field": "is_jo_cos", "lt": 1}},  # unknown comparator
        {"if": {"eq": True}},  # no field
        {"always": "yes"},  # not a boolean
        {"any": {"always": True}},  # not a list
    ],
)
def test_a_malformed_rule_never_raises_and_never_blocks(rule):
    """Evaluation is TOTAL — one bad admin-edited row must not 500 the packet
    screen — and fails OPEN, because with waivers unbuilt a fail-closed block
    would strand the claim with no path (spec §9.1 principle 4). The
    unparseable flag is what surfaces it to a human instead."""
    outcome = evaluate_required_rule(rule, FACTS)
    assert outcome.required is False
    assert outcome.unparseable is True


def test_the_column_default_means_not_required():
    outcome = evaluate_required_rule({}, FACTS)
    assert (outcome.required, outcome.unparseable) == (False, False)
    assert outcome.reason == "empty_rule"


# --- field resolution -------------------------------------------------------


def test_resolve_field_walks_a_dotted_path():
    assert resolve_field(FACTS, "totals.other") == "250.00"
    assert resolve_field(FACTS, "is_jo_cos") is True


def test_resolve_field_projects_across_a_list_of_objects():
    """``sum_matches: {"of": "legs.fare"}`` from spec §5.3, working verbatim."""
    assert resolve_field(FACTS, "legs.fare") == ["500.00", "120.00"]


@pytest.mark.parametrize(
    "path", ["nope", "totals.nope", "totals.other.deeper", "legs.nope", "", 7]
)
def test_resolve_field_returns_missing_rather_than_raising(path):
    assert resolve_field(FACTS, path) is MISSING


def test_a_stored_null_is_not_the_same_as_an_absent_field():
    """`fund_source` is present-and-null; `nope` is absent. A rule may
    legitimately match the first."""
    assert resolve_field(FACTS, "fund_source") is None
    assert resolve_field(FACTS, "nope") is MISSING
    assert required_rule_applies({"if": {"field": "fund_source", "eq": None}}, FACTS)
    assert not required_rule_applies({"if": {"field": "nope", "eq": None}}, FACTS)


def test_every_comparator_is_false_against_a_missing_field():
    for comparator, operand in (("eq", "x"), ("contains", "x"), ("gt", 0)):
        rule = {"if": {"field": "nope", comparator: operand}}
        assert required_rule_applies(rule, FACTS) is False


# --- validation (strict, authoring time) ------------------------------------


def test_validate_accepts_every_shipped_seed_shape():
    for rule in (
        {"always": True},
        {"if": {"field": "is_jo_cos", "eq": True}},
        {"if": {"field": "transport_modes", "contains": "taxi"}},
        {"if": {"field": "totals.other", "gt": 0}},
        {"any": [{"always": True}, {"if": {"field": "x", "eq": 1}}]},
        {"all": [{"always": False}]},
    ):
        validate_required_rule(rule)


@pytest.mark.parametrize(
    "rule",
    [
        {},  # stricter than the evaluator: an authored empty rule is a mistake
        None,
        {"iff": True},
        {"if": {"field": "x"}},
        {"if": {"field": "x", "lt": 1}},
        {"always": "yes"},
        {"any": []},
        {"all": [{"nope": 1}]},
    ],
)
def test_validate_rejects_what_the_evaluator_merely_tolerates(rule):
    with pytest.raises(APIError) as exc:
        validate_required_rule(rule)
    assert exc.value.status_code == 422
    assert exc.value.code.startswith("checklist_")
