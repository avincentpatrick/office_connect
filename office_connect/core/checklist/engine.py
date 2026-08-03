"""Reconciliation + the completeness rule — core-service #7's spine.

Given a catalog, whatever items a subject already has, and the subject's facts,
answer two questions:

1. **What should this subject's checklist look like?** — :func:`plan_checklist`
   returns one :class:`ItemPlan` per applicable-or-evidence-bearing catalog row,
   each carrying the persistence action the consumer should take.
2. **May this subject move on?** — :func:`packet_status` folds the plan into the
   "9 of 12 required items done" progress line, the blocking list a refused
   submit names, and the flags an approver sees.

Pure: dataclasses in, dataclasses out. The consumer owns every query and every
write. That is the whole seam — core owns the *grammar, the semantics and the
reconciliation algorithm* (which is 100% of what DTWIS/QMS/Supply would otherwise
re-derive), while storage stays with the module that already shipped it. When a
second consumer arrives it can hand us its own rows and inherit all of it.

**The decision everything else follows from:**

    Blocking is computed from EVIDENCE STATE, never from the ``status`` column.

``status`` is a derived read-model with exactly one writer — precisely as a claim's
``status`` mirrors the workflow engine rather than being authored by scattered
code. Three consequences fall out for free:

- ``auto_flagged`` counts as **done**. That is the literal encoding of spec §5.3's
  *"a flag never blocks alone"*: an item can be attached AND flagged, the single
  status column says ``auto_flagged``, and the gate does not care because it reads
  the evidence underneath.
- **Check results are never persisted.** They are re-derived on every read, so the
  approver's callouts always describe the claim *as it is now* (spec §9.4) — no
  staleness, no column, no migration.
- A stale ``status`` cannot produce a wrong gate decision, because the gate never
  reads it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Collection, Mapping, Sequence

from office_connect.core.checklist.checks import CheckResult, run_auto_checks
from office_connect.core.checklist.grammar import Facts, evaluate_required_rule

#: The six statuses spec §5.3 defines for a checklist item.
ITEM_STATUSES = (
    "missing",
    "attached",
    "generated",
    "auto_passed",
    "auto_flagged",
    "waived",
)

#: Statuses that mean "this item is done". ``auto_flagged`` is in here on purpose
#: — see the module docstring.
SATISFIED_STATUSES = frozenset(
    {"attached", "generated", "auto_passed", "auto_flagged", "waived"}
)

#: Evidence kinds a human must supply, and therefore the only kinds that can
#: block. Two deliberate exclusions:
#:
#: - ``generated_doc`` — a system-produced artifact cannot be a precondition of
#:   entering the workflow that produces it. Not a temporary dodge around R-5:
#:   it stays true after the template engine ships, because generation happens
#:   downstream of submit. (Without this, the three ``{"always": true}``
#:   generated_doc rows in the shipped catalog would make every claim in the
#:   tenant permanently unsubmittable.)
#: - ``data_only`` — the claim's own data IS the evidence, so there is nothing to
#:   attach and nothing that can be absent. Such an item can still FLAG, which is
#:   how a data problem reaches the reviewer, and a flag never blocks.
BLOCKING_EVIDENCE = frozenset({"upload", "external_wet_sign"})

# Persistence actions a consumer applies to its own rows.
CREATE = "create"
KEEP = "keep"
RESTORE = "restore"
MAKE_DORMANT = "make_dormant"


@dataclass(frozen=True)
class CatalogSpec:
    """One catalog row, as the consumer's table happens to store it."""

    catalog_id: int
    code: str
    label: str
    group: str
    evidence: str
    required_rule: Any = None
    auto_checks: Any = None
    sort: int = 0
    circular_version: str | None = None


@dataclass(frozen=True)
class ItemState:
    """One already-materialized item, plus its evidence tally.

    ``dormant`` means soft-deleted — recoverable, which is what lets a rule that
    stops and then starts applying again restore the same row rather than
    orphaning its history (standing rule 6: never a hard delete).
    """

    item_id: int
    catalog_id: int
    status: str = "missing"
    evidence_count: int = 0
    evidence_pending: int = 0
    evidence_infected: int = 0
    generated: bool = False
    waived: bool = False
    dormant: bool = False

    @property
    def holds_something(self) -> bool:
        """Would deleting this row destroy work someone did?"""
        return bool(self.evidence_count or self.waived or self.generated)


@dataclass(frozen=True)
class ItemPlan:
    """What one catalog row should look like for this subject, and how to get there."""

    catalog: CatalogSpec
    item_id: int | None
    action: str
    required: bool
    rule_reason: str
    unparseable_rule: bool
    evidence_state: str  # missing | attached | generated | waived
    derived_status: str
    checks: tuple[CheckResult, ...] = ()

    @property
    def blocking(self) -> bool:
        return (
            self.required
            and self.evidence_state == "missing"
            and self.catalog.evidence in BLOCKING_EVIDENCE
        )

    @property
    def flags(self) -> tuple[CheckResult, ...]:
        return tuple(check for check in self.checks if check.flagged)


@dataclass(frozen=True)
class BlockingItem:
    """One reason a packet is not ready — everything a refusal message needs."""

    catalog_id: int
    item_id: int | None
    code: str
    label: str
    group: str
    evidence: str
    reason: str = "missing"


@dataclass(frozen=True)
class PacketStatus:
    """The gate's answer, plus the progress line and the approver's flags."""

    required_total: int
    required_done: int
    blocking: tuple[BlockingItem, ...] = ()
    flags: tuple[tuple[int, CheckResult], ...] = ()
    unparseable: tuple[int, ...] = field(default_factory=tuple)

    @property
    def complete(self) -> bool:
        return not self.blocking


# --------------------------------------------------------------------------
# Planning
# --------------------------------------------------------------------------


def _derive(
    spec: CatalogSpec, state: ItemState | None, checks: Sequence[CheckResult]
) -> tuple[str, str]:
    """``(evidence_state, derived_status)`` for one item.

    Precedence is deliberate: a human decision (waive) outranks a machine one
    (generate), which outranks an upload, which outranks the check verdict that
    only *describes* the upload.
    """
    flagged = any(check.flagged for check in checks)
    passed = any(check.outcome == "passed" for check in checks)

    if state is not None and state.waived:
        return ("waived", "waived")
    if state is not None and state.generated:
        return ("generated", "generated")

    if spec.evidence == "data_only":
        # Nothing to attach: the claim's own data is the evidence, so the item is
        # satisfied the moment it applies. The checks decide what to SAY, not
        # whether it counts.
        return ("attached", "auto_flagged" if flagged else "auto_passed")

    if state is not None and state.evidence_count > 0:
        if flagged:
            return ("attached", "auto_flagged")
        if passed:
            return ("attached", "auto_passed")
        return ("attached", "attached")

    return ("missing", "missing")


def _item_facts(facts: Facts, state: ItemState | None) -> dict[str, Any]:
    """Overlay the per-item evidence tally so ``file_present`` can see it."""
    return {
        **facts,
        "item": {
            "evidence_count": state.evidence_count if state else 0,
            "evidence_pending": state.evidence_pending if state else 0,
            "evidence_infected": state.evidence_infected if state else 0,
            "waived": bool(state and state.waived),
            "generated": bool(state and state.generated),
        },
    }


def plan_checklist(
    *,
    catalog: Sequence[CatalogSpec],
    existing: Sequence[ItemState],
    facts: Facts,
) -> tuple[ItemPlan, ...]:
    """Reconcile ``catalog`` against ``existing`` for a subject described by ``facts``.

    Idempotent by construction: the plan is a pure function of its inputs, and
    an applicable row that already exists yields ``KEEP`` — so a consumer that
    only writes on a real change performs zero work on a second call.

    The rule that matters most: **an item that stops applying but already holds
    evidence is never removed.** It stays live, marked not-required, for the UI
    to render as "extra documents you attached". Severing a subject↔document link
    is a records-management act, not a projection refresh — and the file itself
    survives regardless, because the consumer's join row references the subject
    independently.
    """
    by_catalog: dict[int, ItemState] = {state.catalog_id: state for state in existing}
    plans: list[ItemPlan] = []

    for spec in sorted(catalog, key=lambda row: (row.sort, row.code)):
        state = by_catalog.get(spec.catalog_id)
        outcome = evaluate_required_rule(spec.required_rule, facts)
        applies = outcome.required

        if not applies and not outcome.unparseable:
            if state is None:
                continue  # nothing to say and nothing to clean up
            if state.dormant:
                continue  # already put away
        elif outcome.unparseable and state is not None and state.dormant:
            continue
        # An unparseable rule always reaches the plan even with no row behind
        # it: it does not block (see the grammar docstring), so surfacing it is
        # the ONLY way a human learns the catalog needs fixing.

        checks = run_auto_checks(spec.auto_checks, _item_facts(facts, state))
        evidence_state, derived_status = _derive(spec, state, checks)

        if state is None:
            action = CREATE
        elif applies and state.dormant:
            action = RESTORE
        elif applies:
            action = KEEP
        elif state.holds_something:
            action = KEEP
        else:
            action = MAKE_DORMANT

        plans.append(
            ItemPlan(
                catalog=spec,
                item_id=state.item_id if state is not None else None,
                action=action,
                required=applies,
                rule_reason=outcome.reason,
                unparseable_rule=outcome.unparseable,
                evidence_state=evidence_state,
                derived_status=derived_status,
                checks=checks,
            )
        )

    return tuple(plans)


# --------------------------------------------------------------------------
# The completeness rule
# --------------------------------------------------------------------------


def packet_status(
    plan: Sequence[ItemPlan],
    *,
    blocking_evidence: Collection[str] = BLOCKING_EVIDENCE,
) -> PacketStatus:
    """Fold a plan into the gate's answer.

    ``required_total`` counts only items that CAN block — so the progress line
    reads "2 of 2 required items done" rather than dragging in three
    generated-document rows the claimant can do nothing about. A progress bar
    that never reaches the end is worse than no progress bar.
    """
    countable = [
        item
        for item in plan
        if item.required and item.catalog.evidence in blocking_evidence
    ]
    blocking = tuple(
        BlockingItem(
            catalog_id=item.catalog.catalog_id,
            item_id=item.item_id,
            code=item.catalog.code,
            label=item.catalog.label,
            group=item.catalog.group,
            evidence=item.catalog.evidence,
        )
        for item in countable
        if item.evidence_state == "missing"
    )
    flags = tuple(
        (item.catalog.catalog_id, check) for item in plan for check in item.flags
    )
    return PacketStatus(
        required_total=len(countable),
        required_done=len(countable) - len(blocking),
        blocking=blocking,
        flags=flags,
        unparseable=tuple(
            item.catalog.catalog_id for item in plan if item.unparseable_rule
        ),
    )


def status_is_satisfied(status: str) -> bool:
    """Does this item status mean "done"? (The read-model's own view of itself.)"""
    return status in SATISFIED_STATUSES


def validate_status_vocabulary(statuses: Collection[str]) -> None:
    """Assert a consumer's status enum matches core's. Used by the seam contract test."""
    unknown = sorted(set(statuses) - set(ITEM_STATUSES))
    if unknown:
        raise ValueError(f"statuses unknown to the checklist engine: {unknown}")


def catalog_from_mappings(rows: Sequence[Mapping[str, Any]]) -> tuple[CatalogSpec, ...]:
    """Convenience for consumers holding plain dicts (seed verification, tests)."""
    return tuple(
        CatalogSpec(
            catalog_id=int(row["catalog_id"]),
            code=str(row["code"]),
            label=str(row["label"]),
            group=str(row["group"]),
            evidence=str(row["evidence"]),
            required_rule=row.get("required_rule"),
            auto_checks=row.get("auto_checks"),
            sort=int(row.get("sort") or 0),
            circular_version=row.get("circular_version"),
        )
        for row in rows
    )
