"""The shared workflow engine — core-service #1 (master-plan §1.1; Rule 10).

ONE approval/routing engine every module consumes; no module builds its own. Public
surface:

- author a chain: ``create_definition`` / ``create_version`` / ``add_state`` /
  ``add_transition`` / ``publish_version`` (immutable once published) and
  ``get_published_version``;
- run it: ``start_instance`` (the flag gate), ``execute_action`` (the atomic,
  idempotent, CAS transition), ``available_actions`` (the state × actor × guards ×
  delegation set the UI renders and the POST re-validates);
- integrity: ``fold_events`` / ``is_consistent`` (read-model == event log);
- SLA: ``sweep_due_steps`` + ``register_sla_enqueuer`` (ops → core seam).

The engine imports NO module tables — a module's row FKs INTO
``core_workflow_instances`` via the polymorphic ``(subject_kind, subject_id)`` back-ref.
"""

# Leaf-first import order (no submodule imports another that appears below it here).
from office_connect.core.workflow import errors
from office_connect.core.workflow.guards import amount_guard_passes
from office_connect.core.workflow.delegation import Authority, resolve_authority
from office_connect.core.workflow.steps import (
    activate_state_steps,
    gate_steps,
    join_satisfied,
)
from office_connect.core.workflow.replay import (
    fold_events,
    folded_state_id,
    is_consistent,
)
from office_connect.core.workflow.definitions import (
    add_state,
    add_transition,
    create_definition,
    create_version,
    get_published_version,
    initial_state,
    publish_version,
    validate_graph,
)
from office_connect.core.workflow.transitions import available_actions, execute_action
from office_connect.core.workflow.service import start_instance
from office_connect.core.workflow.sla import register_sla_enqueuer, sweep_due_steps

__all__ = [
    "errors",
    # authoring
    "create_definition",
    "create_version",
    "add_state",
    "add_transition",
    "publish_version",
    "validate_graph",
    "get_published_version",
    "initial_state",
    # runtime
    "start_instance",
    "execute_action",
    "available_actions",
    # steps / fan-in
    "activate_state_steps",
    "gate_steps",
    "join_satisfied",
    # delegation
    "Authority",
    "resolve_authority",
    # guards
    "amount_guard_passes",
    # integrity
    "fold_events",
    "folded_state_id",
    "is_consistent",
    # sla
    "sweep_due_steps",
    "register_sla_enqueuer",
]
