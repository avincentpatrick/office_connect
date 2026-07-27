"""The shared workflow engine schema — core-service #1 (master-plan §1.1).

Rule 10's centerpiece: ONE approval/routing engine every module consumes
(reimbursement first, then DTWIS/QMS/supply/plan/perf). No module builds its own
approval machinery. Design basis: docs/research/round1/approval-workflow-engine-
design.md — state-machine-as-data across three concerns:

- **Design-time** (versioned, immutable once published): ``core_workflow_definitions``
  → ``core_workflow_definition_versions`` → ``core_workflow_states`` +
  ``core_workflow_transitions``.
- **Runtime** (small, hot, mutable): ``core_workflow_instances`` (pinned to a
  definition version; carries the CAS ``row_version`` + guard inputs ``amount``/
  ``context``) + ``core_workflow_steps`` (per-approver fan-in rows).
- **History** (append-only, immutable): ``core_workflow_events`` — the authoritative
  audit record; the instance's ``current_state_id`` is a derived read-model
  (``core/workflow/replay.py`` folds the events and asserts they agree).

Plus ``core_workflow_delegations`` — first-class OIC / on-behalf-of (master-plan
§1.1 #1). This *refines* the Stage-B B3 "no RBAC delegation table" decision: a
role-window grants a ROLE; a delegation records that one PERSON exercised another's
authority for a workflow action (events store both ``actor_user_id`` and
``on_behalf_of_user_id``). Different concept, different table.

Repo-convention adaptations of the design doc:
- Authorization is on permission STRINGS (``required_permission``), resolved by
  ``core/org_units.py::authorize_scoped`` — never role names in code. A nullable
  ``required_role_id`` is reserved (unwired) on transitions for a future need.
- The engine imports NO module tables. An instance's business subject is the
  sanctioned polymorphic ``(subject_kind, subject_id)`` back-ref with **no FK**
  (database-standards §3); the module's ``*.workflow_instance_id`` FKs INTO
  ``core_workflow_instances``, never the reverse.
- ``core_workflow_events`` is append-only (``created_*`` only, REVOKE UPDATE) but
  **audited** — it is NOT in ``core/audit.py::_UNAUDITED``, so every event INSERT is
  hash-chained for free. Its free-text/SPI ``payload`` is ``__audit_exclude__`` so
  values never seal into the immutable chain (the field name stays; ``comment`` is
  kept in clear, being the decision rationale COA needs).
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from office_connect.core.base import (
    AuditColsMixin,
    Base,
    PKMixin,
    SoftDeleteMixin,
)

# --- native enums (one source of truth; the DB rows are authoritative) -----

StateKind = Enum(
    "initial", "normal", "terminal", name="core_workflow_state_kind"
)
TransitionAction = Enum(
    "submit",
    "approve",
    "return",
    "reject",
    "cancel",
    "escalate",
    "resubmit",
    name="core_workflow_transition_action",
)
StepStatus = Enum(
    "pending", "active", "done", "returned", "skipped",
    name="core_workflow_step_status",
)
JoinType = Enum("all", "any", "quorum", name="core_workflow_join_type")
EventType = Enum(
    "started", "transition", "escalation", "reminder", "note",
    name="core_workflow_event_type",
)
ResubmitPolicy = Enum(
    "restart", "resume", name="core_workflow_resubmit_policy"
)


# --- design-time: definitions / versions / states / transitions ------------


class WorkflowDefinition(PKMixin, AuditColsMixin, SoftDeleteMixin, Base):
    """A logical workflow (e.g. ``reimbursement.claim``). ``module`` names the
    owning module so a consumer can gate creation on ``module.<x>`` feature flag."""

    __tablename__ = "core_workflow_definitions"
    __table_args__ = (
        Index(
            "uq_core_workflow_definitions_code",
            "code",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_core_workflow_definitions_module", "module"),
    )

    code: Mapped[str]
    name: Mapped[str]
    module: Mapped[str | None]
    description: Mapped[str | None] = mapped_column(Text)


class WorkflowDefinitionVersion(PKMixin, AuditColsMixin, SoftDeleteMixin, Base):
    """An immutable-once-published version of a definition. Instances pin here and
    complete on it even after a newer version publishes (Camunda-style)."""

    __tablename__ = "core_workflow_definition_versions"
    __table_args__ = (
        Index(
            "uq_core_workflow_definition_versions_scope",
            "definition_id",
            "version_no",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_core_workflow_definition_versions_definition_id", "definition_id"
        ),
        # Multiple published (immutable) versions coexist — instances pin to theirs
        # and finish on it; the LATEST published version_no is "current" for new
        # instances (Camunda-style). So no unique-published constraint here.
        Index(
            "ix_core_workflow_definition_versions_published",
            "definition_id",
            postgresql_where=text("is_published AND deleted_at IS NULL"),
        ),
    )

    definition_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("core_workflow_definitions.id")
    )
    version_no: Mapped[int] = mapped_column(Integer)
    is_published: Mapped[bool] = mapped_column(server_default=text("false"))
    published_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    resubmit_policy: Mapped[str] = mapped_column(
        ResubmitPolicy, server_default="restart"
    )


class WorkflowState(PKMixin, AuditColsMixin, SoftDeleteMixin, Base):
    """One node of a version's state graph. An approval-gate state also carries the
    step template: entering it spawns ``step_count`` step rows with
    ``required_permission`` + the instance's org unit, fanned in by ``join_type``.
    (Single-role parallel/four-eyes fits this shape; different-role parallel would
    need a step-def table — deferred until a real requirement, Rule 10.)"""

    __tablename__ = "core_workflow_states"
    __table_args__ = (
        Index(
            "uq_core_workflow_states_code",
            "definition_version_id",
            "code",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_core_workflow_states_definition_version_id", "definition_version_id"
        ),
        # Exactly one initial state per version (validated in code too).
        Index(
            "uq_core_workflow_states_initial",
            "definition_version_id",
            unique=True,
            postgresql_where=text("kind = 'initial' AND deleted_at IS NULL"),
        ),
    )

    definition_version_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("core_workflow_definition_versions.id")
    )
    code: Mapped[str]
    name: Mapped[str]
    kind: Mapped[str] = mapped_column(StateKind, server_default="normal")
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    # Approval-gate config (the step template).
    is_approval_gate: Mapped[bool] = mapped_column(server_default=text("false"))
    required_permission: Mapped[str | None]
    join_type: Mapped[str] = mapped_column(JoinType, server_default="all")
    step_count: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    quorum_count: Mapped[int | None] = mapped_column(Integer)
    sla_hours: Mapped[int | None] = mapped_column(Integer)
    enforce_segregation: Mapped[bool] = mapped_column(server_default=text("false"))
    requires_comment: Mapped[bool] = mapped_column(server_default=text("false"))


class WorkflowTransition(PKMixin, AuditColsMixin, SoftDeleteMixin, Base):
    """A legal move ``from_state --action--> to_state`` with **typed** guards only
    (no DSL): amount band + a required permission + force-a-comment. When several
    transitions share ``(from_state, action)``, the first whose guards pass — by
    ``sort_order`` — fires."""

    __tablename__ = "core_workflow_transitions"
    __table_args__ = (
        Index(
            "ix_core_workflow_transitions_from",
            "from_state_id",
            "action",
            "sort_order",
        ),
        Index(
            "ix_core_workflow_transitions_definition_version_id",
            "definition_version_id",
        ),
    )

    definition_version_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("core_workflow_definition_versions.id")
    )
    from_state_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("core_workflow_states.id")
    )
    to_state_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("core_workflow_states.id")
    )
    action: Mapped[str] = mapped_column(TransitionAction)
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    # Typed guards.
    required_permission: Mapped[str | None]
    min_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    max_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    requires_comment: Mapped[bool] = mapped_column(server_default=text("false"))
    # Reserved, unwired — the repo authorizes on permission strings (see module
    # docstring). Kept for a future role-typed guard need.
    required_role_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("core_roles.id")
    )


# --- runtime: instances / steps --------------------------------------------


class WorkflowInstance(PKMixin, AuditColsMixin, SoftDeleteMixin, Base):
    """A running workflow. ``current_state_id`` is a derived read-model kept in step
    with ``core_workflow_events`` (replay test). ``row_version`` is the optimistic
    lock the CAS transition bumps. ``(subject_kind, subject_id)`` is the sanctioned
    polymorphic back-ref to the owning business row (no FK)."""

    __tablename__ = "core_workflow_instances"
    __table_args__ = (
        Index(
            "ix_core_workflow_instances_subject", "subject_kind", "subject_id"
        ),
        Index(
            "ix_core_workflow_instances_current_state_id", "current_state_id"
        ),
        Index(
            "ix_core_workflow_instances_definition_version_id",
            "definition_version_id",
        ),
        Index("ix_core_workflow_instances_org_unit_id", "org_unit_id"),
        Index(
            "ix_core_workflow_instances_originator_user_id", "originator_user_id"
        ),
    )

    definition_version_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("core_workflow_definition_versions.id")
    )
    current_state_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("core_workflow_states.id")
    )
    row_version: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    revision_no: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    originator_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("core_users.id")
    )
    org_unit_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("core_org_units.id")
    )
    # Polymorphic owner (no FK — database-standards §3). The module's row FKs INTO
    # this table; the engine never resolves the module table.
    subject_kind: Mapped[str | None]
    subject_id: Mapped[int | None] = mapped_column(BigInteger)
    # Guard inputs, populated by the consumer at start/resubmit.
    amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    context: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb")
    )


class WorkflowStep(PKMixin, AuditColsMixin, SoftDeleteMixin, Base):
    """A per-instance approver slot (the fan-in counter). Created when the instance
    enters an approval-gate state; pinned with the state's permission + the
    instance's org unit at activation, so later config edits never re-route it."""

    __tablename__ = "core_workflow_steps"
    __table_args__ = (
        Index("ix_core_workflow_steps_instance_id", "instance_id"),
        Index("ix_core_workflow_steps_state_id", "state_id"),
        Index("ix_core_workflow_steps_status", "status"),
        # SLA sweep target: active steps with a deadline.
        Index(
            "ix_core_workflow_steps_sla_due_at",
            "sla_due_at",
            postgresql_where=text("status = 'active' AND sla_due_at IS NOT NULL"),
        ),
    )

    instance_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("core_workflow_instances.id")
    )
    state_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("core_workflow_states.id")
    )
    # The instance revision this activation belongs to — so a resubmit's fresh steps
    # are fanned in independently of a prior visit's (returned/done) steps.
    revision_no: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    sequence_no: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    join_type: Mapped[str] = mapped_column(JoinType, server_default="all")
    quorum_count: Mapped[int | None] = mapped_column(Integer)
    # Pinned routing (from the state + instance at activation).
    required_permission: Mapped[str | None]
    org_unit_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("core_org_units.id")
    )
    status: Mapped[str] = mapped_column(StepStatus, server_default="pending")
    acted_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("core_users.id")
    )
    on_behalf_of_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("core_users.id")
    )
    acted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    comment: Mapped[str | None] = mapped_column(Text)
    sla_due_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    escalation_level: Mapped[int] = mapped_column(Integer, server_default=text("0"))


# --- history: events (append-only, audited) --------------------------------


class WorkflowEvent(PKMixin, Base):
    """Append-only decision log — the authoritative history. ``created_*`` only +
    REVOKE UPDATE, but **audited** (each INSERT hash-chains). ``payload`` is
    audit-excluded (may carry SPI); ``comment`` is kept in clear (the rationale)."""

    # SPI: free-form payload values never seal into the immutable chain (field name
    # kept). ``comment`` is deliberately NOT excluded — it is the decision reason.
    __audit_exclude__ = frozenset({"payload"})

    __tablename__ = "core_workflow_events"
    __table_args__ = (
        Index("ix_core_workflow_events_instance_id", "instance_id"),
        Index("ix_core_workflow_events_step_id", "step_id"),
        Index("ix_core_workflow_events_event_type", "event_type"),
        # Idempotency: one event per (instance, idempotency_key) — retries replay.
        Index(
            "uq_core_workflow_events_idempotency",
            "instance_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
        # SLA double-fire guard: at most one escalation per (step, level).
        Index(
            "uq_core_workflow_events_escalation",
            "step_id",
            "escalation_level",
            unique=True,
            postgresql_where=text("event_type = 'escalation'"),
        ),
    )

    instance_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("core_workflow_instances.id")
    )
    step_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("core_workflow_steps.id")
    )
    event_type: Mapped[str] = mapped_column(EventType)
    action: Mapped[str | None] = mapped_column(TransitionAction)
    from_state_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("core_workflow_states.id")
    )
    to_state_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("core_workflow_states.id")
    )
    actor_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("core_users.id")
    )
    on_behalf_of_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("core_users.id")
    )
    comment: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb")
    )
    idempotency_key: Mapped[str | None]
    escalation_level: Mapped[int | None] = mapped_column(Integer)
    revision_no: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("core_users.id")
    )


# --- delegation / OIC ------------------------------------------------------


class WorkflowDelegation(PKMixin, AuditColsMixin, SoftDeleteMixin, Base):
    """A time-boxed person→person authority delegation (OIC). Authorization passes
    if the actor is the resolved assignee OR holds an active delegation from someone
    who is; the event records both parties. Scope is optional: a NULL
    ``definition_id``/``org_unit_id`` means "any". Refines B3 (see module docstring)."""

    __tablename__ = "core_workflow_delegations"
    __table_args__ = (
        Index("ix_core_workflow_delegations_delegate_user_id", "delegate_user_id"),
        Index(
            "ix_core_workflow_delegations_delegator_user_id", "delegator_user_id"
        ),
        Index("ix_core_workflow_delegations_window", "starts_at", "ends_at"),
    )

    delegator_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("core_users.id")
    )
    delegate_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("core_users.id")
    )
    definition_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("core_workflow_definitions.id")
    )
    org_unit_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("core_org_units.id")
    )
    starts_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    reason: Mapped[str | None] = mapped_column(Text)
