"""shared workflow engine (core_workflow_*)

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-27

Stage C — the shared core workflow engine (Rule 10 centerpiece; the ONE approval
engine every module consumes). Adds 6 native enums + 8 tables:

- design-time (business): core_workflow_definitions, core_workflow_definition_versions,
  core_workflow_states, core_workflow_transitions
- runtime (business): core_workflow_instances, core_workflow_steps
- history (append-only, REVOKE UPDATE, but audited): core_workflow_events
- delegation (business): core_workflow_delegations

core_workflow_events is append-only: created_* only + ``REVOKE UPDATE FROM oc_app``.
It is NOT in core/audit.py::_UNAUDITED, so every event INSERT hash-chains (the payload
column is redacted from the chain via __audit_exclude__ on the model).

Downgrade drops the tables in reverse-FK order then the enums (checkfirst so a partial
re-run is safe). Idempotent (Alembic revision guard + checkfirst on the enums) and
reversible — validated by tests/test_migrations.py::test_upgrade_head_idempotent.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_ENUMS: dict[str, tuple[str, ...]] = {
    "core_workflow_state_kind": ("initial", "normal", "terminal"),
    "core_workflow_transition_action": (
        "submit", "approve", "return", "reject", "cancel", "escalate", "resubmit",
    ),
    "core_workflow_step_status": (
        "pending", "active", "done", "returned", "skipped",
    ),
    "core_workflow_join_type": ("all", "any", "quorum"),
    "core_workflow_event_type": (
        "started", "transition", "escalation", "reminder", "note",
    ),
    "core_workflow_resubmit_policy": ("restart", "resume"),
}


def _enum(name: str):
    """Reference an already-created native enum (never re-create the type)."""
    return postgresql.ENUM(name=name, create_type=False)


def _audit_soft_delete_cols() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("updated_by", sa.BigInteger(), nullable=True),
        sa.Column("deleted_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("deleted_by", sa.BigInteger(), nullable=True),
    ]


def _fk(table: str, col: str, ref_table: str, ref_col: str = "id"):
    return sa.ForeignKeyConstraint(
        [col],
        [f"{ref_table}.{ref_col}"],
        name=op.f(f"fk_{table}_{col}_{ref_table}"),
    )


def _owner_fks(table: str) -> list[sa.ForeignKeyConstraint]:
    return [_fk(table, c, "core_users") for c in ("created_by", "updated_by", "deleted_by")]


def _pk(table: str):
    return sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table}"))


def _id_col() -> sa.Column:
    return sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False)


def upgrade() -> None:
    bind = op.get_bind()
    for name, values in _ENUMS.items():
        postgresql.ENUM(*values, name=name).create(bind, checkfirst=True)

    # 1. definitions
    t = "core_workflow_definitions"
    op.create_table(
        t,
        _id_col(),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("module", sa.String(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        *_audit_soft_delete_cols(),
        _pk(t),
        *_owner_fks(t),
    )
    op.create_index(
        "uq_core_workflow_definitions_code", t, ["code"], unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index("ix_core_workflow_definitions_module", t, ["module"])

    # 2. definition_versions
    t = "core_workflow_definition_versions"
    op.create_table(
        t,
        _id_col(),
        sa.Column("definition_id", sa.BigInteger(), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column(
            "is_published", sa.Boolean(), server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("published_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "resubmit_policy", _enum("core_workflow_resubmit_policy"),
            server_default="restart", nullable=False,
        ),
        *_audit_soft_delete_cols(),
        _pk(t),
        _fk(t, "definition_id", "core_workflow_definitions"),
        *_owner_fks(t),
    )
    op.create_index(
        "uq_core_workflow_definition_versions_scope", t,
        ["definition_id", "version_no"], unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_core_workflow_definition_versions_definition_id", t, ["definition_id"],
    )
    op.create_index(
        "ix_core_workflow_definition_versions_published", t, ["definition_id"],
        postgresql_where=sa.text("is_published AND deleted_at IS NULL"),
    )

    # 3. states
    t = "core_workflow_states"
    op.create_table(
        t,
        _id_col(),
        sa.Column("definition_version_id", sa.BigInteger(), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column(
            "kind", _enum("core_workflow_state_kind"),
            server_default="normal", nullable=False,
        ),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "is_approval_gate", sa.Boolean(), server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("required_permission", sa.String(), nullable=True),
        sa.Column(
            "join_type", _enum("core_workflow_join_type"),
            server_default="all", nullable=False,
        ),
        sa.Column("step_count", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("quorum_count", sa.Integer(), nullable=True),
        sa.Column("sla_hours", sa.Integer(), nullable=True),
        sa.Column(
            "enforce_segregation", sa.Boolean(), server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "requires_comment", sa.Boolean(), server_default=sa.text("false"),
            nullable=False,
        ),
        *_audit_soft_delete_cols(),
        _pk(t),
        _fk(t, "definition_version_id", "core_workflow_definition_versions"),
        *_owner_fks(t),
    )
    op.create_index(
        "uq_core_workflow_states_code", t, ["definition_version_id", "code"],
        unique=True, postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_core_workflow_states_definition_version_id", t, ["definition_version_id"],
    )
    op.create_index(
        "uq_core_workflow_states_initial", t, ["definition_version_id"], unique=True,
        postgresql_where=sa.text("kind = 'initial' AND deleted_at IS NULL"),
    )

    # 4. transitions
    t = "core_workflow_transitions"
    op.create_table(
        t,
        _id_col(),
        sa.Column("definition_version_id", sa.BigInteger(), nullable=False),
        sa.Column("from_state_id", sa.BigInteger(), nullable=False),
        sa.Column("to_state_id", sa.BigInteger(), nullable=False),
        sa.Column("action", _enum("core_workflow_transition_action"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("required_permission", sa.String(), nullable=True),
        sa.Column("min_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("max_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column(
            "requires_comment", sa.Boolean(), server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("required_role_id", sa.BigInteger(), nullable=True),
        *_audit_soft_delete_cols(),
        _pk(t),
        _fk(t, "definition_version_id", "core_workflow_definition_versions"),
        _fk(t, "from_state_id", "core_workflow_states"),
        _fk(t, "to_state_id", "core_workflow_states"),
        _fk(t, "required_role_id", "core_roles"),
        *_owner_fks(t),
    )
    op.create_index(
        "ix_core_workflow_transitions_from", t,
        ["from_state_id", "action", "sort_order"],
    )
    op.create_index(
        "ix_core_workflow_transitions_definition_version_id", t,
        ["definition_version_id"],
    )

    # 5. instances
    t = "core_workflow_instances"
    op.create_table(
        t,
        _id_col(),
        sa.Column("definition_version_id", sa.BigInteger(), nullable=False),
        sa.Column("current_state_id", sa.BigInteger(), nullable=False),
        sa.Column("row_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("revision_no", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("originator_user_id", sa.BigInteger(), nullable=True),
        sa.Column("org_unit_id", sa.BigInteger(), nullable=True),
        sa.Column("subject_kind", sa.String(), nullable=True),
        sa.Column("subject_id", sa.BigInteger(), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=True),
        sa.Column(
            "context", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        *_audit_soft_delete_cols(),
        _pk(t),
        _fk(t, "definition_version_id", "core_workflow_definition_versions"),
        _fk(t, "current_state_id", "core_workflow_states"),
        _fk(t, "originator_user_id", "core_users"),
        _fk(t, "org_unit_id", "core_org_units"),
        *_owner_fks(t),
    )
    op.create_index(
        "ix_core_workflow_instances_subject", t, ["subject_kind", "subject_id"],
    )
    op.create_index(
        "ix_core_workflow_instances_current_state_id", t, ["current_state_id"],
    )
    op.create_index(
        "ix_core_workflow_instances_definition_version_id", t,
        ["definition_version_id"],
    )
    op.create_index("ix_core_workflow_instances_org_unit_id", t, ["org_unit_id"])
    op.create_index(
        "ix_core_workflow_instances_originator_user_id", t, ["originator_user_id"],
    )

    # 6. steps
    t = "core_workflow_steps"
    op.create_table(
        t,
        _id_col(),
        sa.Column("instance_id", sa.BigInteger(), nullable=False),
        sa.Column("state_id", sa.BigInteger(), nullable=False),
        sa.Column("revision_no", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("sequence_no", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "join_type", _enum("core_workflow_join_type"),
            server_default="all", nullable=False,
        ),
        sa.Column("quorum_count", sa.Integer(), nullable=True),
        sa.Column("required_permission", sa.String(), nullable=True),
        sa.Column("org_unit_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "status", _enum("core_workflow_step_status"),
            server_default="pending", nullable=False,
        ),
        sa.Column("acted_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column("on_behalf_of_user_id", sa.BigInteger(), nullable=True),
        sa.Column("acted_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("sla_due_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "escalation_level", sa.Integer(), server_default=sa.text("0"),
            nullable=False,
        ),
        *_audit_soft_delete_cols(),
        _pk(t),
        _fk(t, "instance_id", "core_workflow_instances"),
        _fk(t, "state_id", "core_workflow_states"),
        _fk(t, "org_unit_id", "core_org_units"),
        _fk(t, "acted_by_user_id", "core_users"),
        _fk(t, "on_behalf_of_user_id", "core_users"),
        *_owner_fks(t),
    )
    op.create_index("ix_core_workflow_steps_instance_id", t, ["instance_id"])
    op.create_index("ix_core_workflow_steps_state_id", t, ["state_id"])
    op.create_index("ix_core_workflow_steps_status", t, ["status"])
    op.create_index(
        "ix_core_workflow_steps_sla_due_at", t, ["sla_due_at"],
        postgresql_where=sa.text("status = 'active' AND sla_due_at IS NOT NULL"),
    )

    # 7. events (append-only, audited)
    t = "core_workflow_events"
    op.create_table(
        t,
        _id_col(),
        sa.Column("instance_id", sa.BigInteger(), nullable=False),
        sa.Column("step_id", sa.BigInteger(), nullable=True),
        sa.Column("event_type", _enum("core_workflow_event_type"), nullable=False),
        sa.Column("action", _enum("core_workflow_transition_action"), nullable=True),
        sa.Column("from_state_id", sa.BigInteger(), nullable=True),
        sa.Column("to_state_id", sa.BigInteger(), nullable=True),
        sa.Column("actor_user_id", sa.BigInteger(), nullable=True),
        sa.Column("on_behalf_of_user_id", sa.BigInteger(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "payload", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(), nullable=True),
        sa.Column("escalation_level", sa.Integer(), nullable=True),
        sa.Column("revision_no", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        _pk(t),
        _fk(t, "instance_id", "core_workflow_instances"),
        _fk(t, "step_id", "core_workflow_steps"),
        _fk(t, "from_state_id", "core_workflow_states"),
        _fk(t, "to_state_id", "core_workflow_states"),
        _fk(t, "actor_user_id", "core_users"),
        _fk(t, "on_behalf_of_user_id", "core_users"),
        _fk(t, "created_by", "core_users"),
    )
    op.create_index("ix_core_workflow_events_instance_id", t, ["instance_id"])
    op.create_index("ix_core_workflow_events_step_id", t, ["step_id"])
    op.create_index("ix_core_workflow_events_event_type", t, ["event_type"])
    op.create_index(
        "uq_core_workflow_events_idempotency", t,
        ["instance_id", "idempotency_key"], unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.create_index(
        "uq_core_workflow_events_escalation", t, ["step_id", "escalation_level"],
        unique=True, postgresql_where=sa.text("event_type = 'escalation'"),
    )
    # Append-only: no row may ever be UPDATEd by the runtime role.
    op.execute("REVOKE UPDATE ON core_workflow_events FROM oc_app")

    # 8. delegations
    t = "core_workflow_delegations"
    op.create_table(
        t,
        _id_col(),
        sa.Column("delegator_user_id", sa.BigInteger(), nullable=False),
        sa.Column("delegate_user_id", sa.BigInteger(), nullable=False),
        sa.Column("definition_id", sa.BigInteger(), nullable=True),
        sa.Column("org_unit_id", sa.BigInteger(), nullable=True),
        sa.Column("starts_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("ends_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        *_audit_soft_delete_cols(),
        _pk(t),
        _fk(t, "delegator_user_id", "core_users"),
        _fk(t, "delegate_user_id", "core_users"),
        _fk(t, "definition_id", "core_workflow_definitions"),
        _fk(t, "org_unit_id", "core_org_units"),
        *_owner_fks(t),
    )
    op.create_index(
        "ix_core_workflow_delegations_delegate_user_id", t, ["delegate_user_id"],
    )
    op.create_index(
        "ix_core_workflow_delegations_delegator_user_id", t, ["delegator_user_id"],
    )
    op.create_index(
        "ix_core_workflow_delegations_window", t, ["starts_at", "ends_at"],
    )


def downgrade() -> None:
    # Reverse-FK order.
    for t in (
        "core_workflow_delegations",
        "core_workflow_events",
        "core_workflow_steps",
        "core_workflow_instances",
        "core_workflow_transitions",
        "core_workflow_states",
        "core_workflow_definition_versions",
        "core_workflow_definitions",
    ):
        op.drop_table(t)
    bind = op.get_bind()
    for name in _ENUMS:
        postgresql.ENUM(name=name).drop(bind, checkfirst=True)
