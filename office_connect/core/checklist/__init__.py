"""The shared checklist engine — core-service #7 (master-plan §1.1; Rule 10).

ONE documentary-requirements engine every module consumes; no module builds its
own rule interpreter. Generalized from the reimbursement build spec §5.3, whose
grammar it implements verbatim and closed.

Public surface:

- **grammar** — ``evaluate_required_rule`` / ``required_rule_applies`` (total,
  never raises) and ``validate_required_rule`` (strict, authoring time);
- **checks** — ``run_auto_checks`` / ``checks_outcome`` over the six spec §5.3
  check types, plus ``validate_auto_checks``;
- **engine** — ``plan_checklist`` (idempotent reconciliation: create / keep /
  restore / make_dormant) and ``packet_status`` (the progress line, the blocking
  list, the reviewer's flags).

**The seam.** This package is pure: dataclasses in, dataclasses out, no I/O, no
ORM, no session. A consumer keeps its own catalog/item tables, assembles a
``facts`` mapping from them, and applies the returned plan itself. Core therefore
imports no module table — the same discipline ``core/workflow`` states in its own
docstring, and what keeps the import-linter contract true by construction.

Storage promotion (``core_checklist_*`` tables) is deliberately deferred until a
second consumer exists to say which columns are genuinely common; the reusable
asset — grammar, check semantics, reconciliation, the blocking rule — is here now.
"""

# Leaf-first import order (no submodule imports another that appears below it).
from office_connect.core.checklist import errors
from office_connect.core.checklist.grammar import (
    COMPARATORS,
    MAX_RULE_DEPTH,
    MISSING,
    RULE_OPERATORS,
    Facts,
    RuleOutcome,
    evaluate_required_rule,
    required_rule_applies,
    resolve_field,
    validate_required_rule,
)
from office_connect.core.checklist.checks import (
    CHECK_TYPES,
    FLAGGED,
    PASSED,
    SKIPPED,
    CheckResult,
    checks_outcome,
    run_auto_checks,
    validate_auto_checks,
)
from office_connect.core.checklist.engine import (
    BLOCKING_EVIDENCE,
    CREATE,
    ITEM_STATUSES,
    KEEP,
    MAKE_DORMANT,
    RESTORE,
    SATISFIED_STATUSES,
    BlockingItem,
    CatalogSpec,
    ItemPlan,
    ItemState,
    PacketStatus,
    catalog_from_mappings,
    plan_checklist,
    packet_status,
    status_is_satisfied,
    validate_status_vocabulary,
)

__all__ = [
    "errors",
    # grammar
    "Facts",
    "MISSING",
    "RULE_OPERATORS",
    "COMPARATORS",
    "MAX_RULE_DEPTH",
    "RuleOutcome",
    "resolve_field",
    "evaluate_required_rule",
    "required_rule_applies",
    "validate_required_rule",
    # checks
    "CHECK_TYPES",
    "PASSED",
    "FLAGGED",
    "SKIPPED",
    "CheckResult",
    "run_auto_checks",
    "checks_outcome",
    "validate_auto_checks",
    # engine
    "CatalogSpec",
    "ItemState",
    "ItemPlan",
    "BlockingItem",
    "PacketStatus",
    "ITEM_STATUSES",
    "SATISFIED_STATUSES",
    "BLOCKING_EVIDENCE",
    "CREATE",
    "KEEP",
    "RESTORE",
    "MAKE_DORMANT",
    "plan_checklist",
    "packet_status",
    "status_is_satisfied",
    "validate_status_vocabulary",
    "catalog_from_mappings",
]
