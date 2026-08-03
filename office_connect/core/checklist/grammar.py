"""The ``required_rule`` grammar — core-service #7's first half (master-plan §1.1).

Pure, total, no I/O: the same shape as ``core/workflow/guards.py``. A consuming
module hands in plain ``facts`` (a mapping it assembled from its own tables) and a
rule (JSONB from its own catalog); this module answers "is this item required?".
Core never sees a module table — that is what keeps the import contract
(``pyproject.toml``: *core never imports modules*) true by construction.

**Operator set — build spec §5.3, verbatim and closed:**

.. code-block:: json

    {"always": true}
    {"if": {"field": "is_jo_cos", "eq": true}}
    {"if": {"field": "transport_modes", "contains": "taxi"}}
    {"if": {"field": "totals.other", "gt": 0}}
    {"any": [ {...}, {...} ]}   {"all": [ {...}, {...} ]}

The spec says "the builder implements **exactly** these operators", and it is
right to: every operator that appears in seeded JSONB is a forever contract — a
catalog row written against it outlives the code that added it. ``_COMPARATORS``
is a dict so a future ``lt``/``in`` is one entry plus one test, deliberately not
pre-added.

**Sanctioned divergence from the workflow engine.** ``core/workflow/guards.py``
says routing guards are "typed columns, never a free-form expression language
(PITFALL)". This is not that pitfall: the operator set is closed, enumerated and
validated, there is no user-supplied code path, and the catalog is an
admin-editable lookup table whose rule grammar ``database-standards.md`` §11
explicitly sanctions as JSONB. Routing money through a DSL would be unauditable;
asking "did you attach the taxi receipt?" through a 4-operator grammar is the
whole point of a configurable documentary-requirements engine.

**Evaluation is TOTAL; validation is STRICT.** ``evaluate_required_rule`` runs on
every packet read, over JSONB an administrator can edit — one malformed row must
never 500 the Documents screen. ``validate_required_rule`` raises, and runs at
seed / authoring time where a loud failure is exactly what you want.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

from office_connect.core.checklist import errors

Facts = Mapping[str, Any]

RULE_OPERATORS = frozenset({"always", "if", "any", "all"})
COMPARATORS = frozenset({"eq", "contains", "gt"})

#: Guards against a self-referential / pathological catalog row. Nothing in the
#: spec's grammar needs more than 2 levels; 8 is generous and still terminates.
MAX_RULE_DEPTH = 8


class _Missing:
    """Sentinel for "this path does not exist in the facts".

    Deliberately NOT ``None``: a fact that is *present and null* (an unset
    ``fund_source``, say) is a real value a rule may legitimately match with
    ``{"eq": null}``. Conflating the two would make "we never asked" and "the
    answer is nothing" indistinguishable.
    """

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "MISSING"

    def __bool__(self) -> bool:
        return False


MISSING = _Missing()


@dataclass(frozen=True)
class RuleOutcome:
    """Why an item is (or is not) required — the reason travels to the UI."""

    required: bool
    #: Machine slug: always | condition_met | condition_unmet | empty_rule |
    #: any_satisfied | any_unsatisfied | all_satisfied | all_unsatisfied |
    #: unparseable_rule
    reason: str
    unparseable: bool = False


# --------------------------------------------------------------------------
# Field resolution
# --------------------------------------------------------------------------


def resolve_field(facts: Facts, path: str) -> Any:
    """Resolve a dotted ``path`` against ``facts``, or ``MISSING``.

    Two behaviours beyond plain mapping traversal:

    - **List projection.** When a segment lands on a sequence of mappings, the
      remaining segment is projected across it — so ``"legs.fare"`` yields
      ``["500.00", "450.00"]``, which is what spec §5.3's
      ``sum_matches: {"of": "legs.fare"}`` means verbatim.
    - **Fail-soft traversal.** Any step through a non-mapping, or a missing key,
      returns ``MISSING`` rather than raising. Every comparator is ``False``
      against ``MISSING``, so a typo'd field name makes a rule not-apply rather
      than exploding — and ``validate_required_rule`` is where typos get caught.
    """
    if not isinstance(path, str) or not path:
        return MISSING

    current: Any = facts
    for segment in path.split("."):
        if isinstance(current, Mapping):
            if segment not in current:
                return MISSING
            current = current[segment]
        elif isinstance(current, Sequence) and not isinstance(current, (str, bytes)):
            projected = [
                item[segment]
                for item in current
                if isinstance(item, Mapping) and segment in item
            ]
            if not projected:
                return MISSING
            current = projected
        else:
            return MISSING
    return current


# --------------------------------------------------------------------------
# Comparators
# --------------------------------------------------------------------------


def _as_decimal(value: Any) -> Decimal | None:
    """Coerce a money-ish value to ``Decimal``, or ``None`` if it is not numeric.

    Money crosses this codebase as a **2-dp string** (``core/money.py`` —
    ``"250.00"``), so ``{"gt": 0}`` against ``totals.other`` compares a string to
    an int. Without this coercion the only conditional-money rule in the shipped
    catalog (LOD-01) would silently never fire. ``bool`` is excluded on purpose:
    ``True`` is not the number 1 in a requirements rule.
    """
    if isinstance(value, bool) or value is None or isinstance(value, _Missing):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float, str)):
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None
    return None


def _cmp_eq(actual: Any, expected: Any) -> bool:
    if isinstance(actual, _Missing):
        return False
    # Booleans are their own type here, never 1/0: Python says ``True == 1``,
    # but a rule asking "is the claimant JO/COS?" must not be satisfied by an
    # integer. Coercion is for money strings, not for truth values.
    if isinstance(actual, bool) or isinstance(expected, bool):
        return type(actual) is type(expected) and actual == expected
    left, right = _as_decimal(actual), _as_decimal(expected)
    if left is not None and right is not None:
        return left == right
    return bool(actual == expected)


def _cmp_contains(actual: Any, expected: Any) -> bool:
    if isinstance(actual, _Missing):
        return False
    if isinstance(actual, str):
        return isinstance(expected, str) and expected in actual
    if isinstance(actual, (Sequence, set, frozenset)) and not isinstance(
        actual, (str, bytes)
    ):
        return expected in actual
    return False


def _cmp_gt(actual: Any, expected: Any) -> bool:
    left, right = _as_decimal(actual), _as_decimal(expected)
    if left is None or right is None:
        return False
    return left > right


_COMPARATORS = {"eq": _cmp_eq, "contains": _cmp_contains, "gt": _cmp_gt}


# --------------------------------------------------------------------------
# Evaluation (total — never raises)
# --------------------------------------------------------------------------


_UNPARSEABLE = RuleOutcome(required=False, reason="unparseable_rule", unparseable=True)


def evaluate_required_rule(rule: Any, facts: Facts) -> RuleOutcome:
    """Is an item with this ``required_rule`` required, given ``facts``?

    **Never raises.** Two failure directions, and the choice between them is a
    policy decision worth stating:

    - ``{}`` (the column's ``server_default``) and ``{"always": false}`` →
      **not required**. An explicit, understood statement.
    - Anything malformed → **not required, flagged ``unparseable``**. The
      consumer surfaces it to a reviewer as a flag rather than blocking on it.

      Failing *closed* (block on an unparseable rule) is the compliance-safe
      direction and is what we want eventually — but it needs a waiver path to
      escape, and waivers are not built (R-3 kickoff decision). Blocking with no
      escape strands a claim forever, which spec §9.1 principle 4 ("never block
      without a path") forbids outright. The catalog is seed-only until the
      admin editor ships and ``validate_required_rule`` gates the seeds, so an
      unparseable rule cannot reach data today. **When the catalog editor ships,
      waivers must ship with it and this flips to fail-closed.**
    """
    return _evaluate(rule, facts, depth=0)


def _evaluate(rule: Any, facts: Facts, *, depth: int) -> RuleOutcome:
    if depth > MAX_RULE_DEPTH:
        return _UNPARSEABLE
    if rule is None:
        return _UNPARSEABLE
    if not isinstance(rule, Mapping):
        return _UNPARSEABLE
    if not rule:
        return RuleOutcome(required=False, reason="empty_rule")
    if len(rule) != 1:
        # Two operators in one node is ambiguous (is it and-ed? or-ed?). `all`
        # exists to say so explicitly.
        return _UNPARSEABLE

    operator, operand = next(iter(rule.items()))
    if operator == "always":
        if not isinstance(operand, bool):
            return _UNPARSEABLE
        return RuleOutcome(
            required=operand, reason="always" if operand else "empty_rule"
        )
    if operator == "if":
        return _evaluate_condition(operand, facts)
    if operator in ("any", "all"):
        return _evaluate_junction(operator, operand, facts, depth=depth)
    return _UNPARSEABLE


def _evaluate_condition(operand: Any, facts: Facts) -> RuleOutcome:
    if not isinstance(operand, Mapping) or "field" not in operand:
        return _UNPARSEABLE
    comparators = [key for key in operand if key != "field"]
    if len(comparators) != 1 or comparators[0] not in _COMPARATORS:
        return _UNPARSEABLE

    comparator = comparators[0]
    actual = resolve_field(facts, operand["field"])
    matched = _COMPARATORS[comparator](actual, operand[comparator])
    return RuleOutcome(
        required=matched,
        reason="condition_met" if matched else "condition_unmet",
    )


def _evaluate_junction(
    operator: str, operand: Any, facts: Facts, *, depth: int
) -> RuleOutcome:
    if not isinstance(operand, Sequence) or isinstance(operand, (str, bytes)):
        return _UNPARSEABLE

    outcomes = [_evaluate(branch, facts, depth=depth + 1) for branch in operand]
    if any(outcome.unparseable for outcome in outcomes):
        # One rotten branch poisons the node: we cannot honestly say the
        # junction was satisfied when we could not read part of it.
        return _UNPARSEABLE

    if operator == "any":
        # Vacuously false: "required if any of nothing" requires nothing.
        matched = any(outcome.required for outcome in outcomes)
        return RuleOutcome(
            required=matched,
            reason="any_satisfied" if matched else "any_unsatisfied",
        )
    # Vacuously true, matching boolean algebra — but an empty `all` is also a
    # catalog-authoring mistake, which `validate_required_rule` rejects.
    matched = all(outcome.required for outcome in outcomes)
    return RuleOutcome(
        required=matched,
        reason="all_satisfied" if matched else "all_unsatisfied",
    )


def required_rule_applies(rule: Any, facts: Facts) -> bool:
    """Boolean shorthand over :func:`evaluate_required_rule`."""
    return evaluate_required_rule(rule, facts).required


# --------------------------------------------------------------------------
# Validation (strict — raises; authoring/seed time only)
# --------------------------------------------------------------------------


def validate_required_rule(rule: Any) -> None:
    """Raise ``APIError`` unless ``rule`` is a well-formed requirement rule.

    Stricter than the evaluator on purpose: ``{}`` evaluates to "not required"
    (it is the column default and must not break reads) but is rejected here,
    because a catalog row someone deliberately authored with an empty rule is
    always a mistake — say ``{"always": false}`` if you mean it.
    """
    _validate(rule, depth=0)


def _validate(rule: Any, *, depth: int) -> None:
    if depth > MAX_RULE_DEPTH:
        raise errors.invalid_rule(f"nested deeper than {MAX_RULE_DEPTH} levels")
    if not isinstance(rule, Mapping):
        raise errors.invalid_rule(f"expected an object, got {type(rule).__name__}")
    if not rule:
        raise errors.invalid_rule(
            "the rule is empty — use {\"always\": false} to mean 'never required'"
        )
    if len(rule) != 1:
        raise errors.invalid_rule(
            f"expected exactly one operator, got {sorted(rule)} — "
            "combine them with 'all' or 'any'"
        )

    operator, operand = next(iter(rule.items()))
    if operator not in RULE_OPERATORS:
        raise errors.unknown_rule_operator(str(operator))

    if operator == "always":
        if not isinstance(operand, bool):
            raise errors.invalid_rule("'always' takes true or false")
        return

    if operator == "if":
        if not isinstance(operand, Mapping):
            raise errors.invalid_rule("'if' takes an object")
        if "field" not in operand or not isinstance(operand["field"], str):
            raise errors.invalid_rule("'if' needs a string 'field'")
        comparators = [key for key in operand if key != "field"]
        if len(comparators) != 1:
            raise errors.invalid_rule(
                f"'if' needs exactly one comparator, got {sorted(comparators)}"
            )
        if comparators[0] not in COMPARATORS:
            raise errors.unknown_comparator(str(comparators[0]))
        return

    if not isinstance(operand, Sequence) or isinstance(operand, (str, bytes)):
        raise errors.invalid_rule(f"'{operator}' takes a list of rules")
    if not operand:
        raise errors.invalid_rule(f"'{operator}' has no branches")
    for branch in operand:
        _validate(branch, depth=depth + 1)
