"""identity FK closure — constrain every deferred *_by / actor / org column

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-23

Stage B (Phase 2) Increment 1. The single migration that realizes the "future FK
core_users.id" promise Increments 1–4 deferred: it adds the referential
constraints for every ownership/actor/org column now that ``core_users`` and
``core_org_units`` exist (0009). Paired with the ``ForeignKey`` added to the
shared ``AuditColsMixin`` / ``SoftDeleteMixin`` columns and the bespoke log
columns in the models — so the ORM metadata and the DB agree (compare_type +
compare_server_default are on).

Every pre-existing ``*_by`` / ``actor_id`` value is NULL (Increments 1–4 wrote as
the owner role, never a user), so each constraint validates against zero non-null
rows — no backfill. ``core_users`` carries a legal nullable self-FK on its own
``*_by`` columns. Sanctioned polymorphic / generic-pointer columns
(``core_attachments.(holder_kind, holder_id)``, ``core_audit_logs.row_pk``) are
deliberately left unconstrained (database-standards §3).

Note: the model ``ForeignKey`` edits (base.py mixin + bespoke columns) are not
migration-controlled, so a downgrade leaves the ORM models ahead of the DB —
acceptable for dev-only downgrades.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Business + lookup tables carrying the full created_by/updated_by/deleted_by set,
# each → core_users.id (the mixin closure).
_USER_FK_TABLES: tuple[str, ...] = (
    # pre-existing (Increments 1–4)
    "core_tenant_configs",
    "core_feature_flags",
    "core_activities",
    "core_activity_tags",
    "core_activity_tag_assignments",
    "core_attachments",
    "core_compliance_deadlines",
    "core_holidays",
    "core_notifications",
    "core_object_codes",
    "core_pap_codes",
    # new in B1 (0009)
    "core_org_units",
    "core_staff",
    "core_users",  # legal nullable self-reference
    "core_roles",
    "core_permissions",
    "core_role_permissions",
    "core_user_roles",
)
_BY_COLS: tuple[str, ...] = ("created_by", "updated_by", "deleted_by")

# Bespoke single-column deferred FKs: (table, column, referent_table).
_BESPOKE_FKS: tuple[tuple[str, str, str], ...] = (
    ("core_audit_logs", "actor_id", "core_users"),
    ("core_query_logs", "created_by", "core_users"),
    ("core_notification_deliveries", "created_by", "core_users"),
    ("core_report_lineages", "created_by", "core_users"),
    ("core_report_lineages", "generated_by", "core_users"),
    ("core_attachments", "disposed_by", "core_users"),
    ("core_notifications", "recipient_user_id", "core_users"),
    ("core_activities", "division_id", "core_org_units"),
    ("core_activities", "section_id", "core_org_units"),
    ("core_compliance_deadlines", "tenant_id", "core_tenant_configs"),
)


def upgrade() -> None:
    for table in _USER_FK_TABLES:
        for col in _BY_COLS:
            op.create_foreign_key(
                op.f(f"fk_{table}_{col}_core_users"),
                table,
                "core_users",
                [col],
                ["id"],
            )
    for table, col, ref in _BESPOKE_FKS:
        op.create_foreign_key(
            op.f(f"fk_{table}_{col}_{ref}"),
            table,
            ref,
            [col],
            ["id"],
        )


def downgrade() -> None:
    for table, col, ref in reversed(_BESPOKE_FKS):
        op.drop_constraint(op.f(f"fk_{table}_{col}_{ref}"), table, type_="foreignkey")
    for table in reversed(_USER_FK_TABLES):
        for col in reversed(_BY_COLS):
            op.drop_constraint(
                op.f(f"fk_{table}_{col}_core_users"), table, type_="foreignkey"
            )
