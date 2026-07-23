"""identity schema — org units, staff directory, users, roles, permissions, grants

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-23

Stage B (Phase 2) Increment 1, master-plan §2 Stage B + §1.1 #14. The identity
floor: the self-referencing org-unit tree, the split person-directory
(``core_staff``) / auth-account (``core_users``) model, the RBAC tables
(roles / permissions / role→permission / user→role scoped grants), and the
append-only ``core_login_attempts`` log.

- Mutable tables (org_units, staff, users, roles, permissions, role_permissions,
  user_roles) inherit oc_app SELECT/INSERT/UPDATE from 0001's default privileges
  — no explicit GRANT here.
- ``core_login_attempts`` is append-only — created_* only; MUST REVOKE UPDATE.
- Structural FKs (parent, staff↔org, user↔staff, grant links, login→user) are
  inline here. The ``*_by`` / ``actor_id`` referential closure to core_users
  across the WHOLE spine is migration 0010.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _audit_soft_delete_cols() -> list[sa.Column]:
    """Mandatory business/lookup columns (database-standards §6). The ``*_by``
    columns are plain BIGINT here; migration 0010 adds their core_users FK."""
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


def upgrade() -> None:
    org_unit_kind = postgresql.ENUM(
        "office", "division", "section", "unit", name="core_org_unit_kind"
    )
    org_unit_kind.create(op.get_bind(), checkfirst=True)
    employment_status = postgresql.ENUM(
        "permanent",
        "temporary",
        "casual",
        "coterminous",
        "contractual",
        "contract_of_service",
        "job_order",
        name="core_employment_status",
    )
    employment_status.create(op.get_bind(), checkfirst=True)
    auth_source = postgresql.ENUM("local", "ldap", name="core_auth_source")
    auth_source.create(op.get_bind(), checkfirst=True)
    login_outcome = postgresql.ENUM(
        "success",
        "failure",
        "throttled",
        "mfa_required",
        "mfa_failure",
        name="core_login_outcome",
    )
    login_outcome.create(op.get_bind(), checkfirst=True)

    # ---------------------------------------------------------- core_org_units
    op.create_table(
        "core_org_units",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column(
            "kind",
            postgresql.ENUM(name="core_org_unit_kind", create_type=False),
            nullable=False,
        ),
        sa.Column("parent_org_unit_id", sa.BigInteger(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        *_audit_soft_delete_cols(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_core_org_units")),
        sa.ForeignKeyConstraint(
            ["parent_org_unit_id"],
            ["core_org_units.id"],
            name=op.f("fk_core_org_units_parent_org_unit_id_core_org_units"),
        ),
    )
    op.create_index(
        "uq_core_org_units_code",
        "core_org_units",
        ["code"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_core_org_units_parent_org_unit_id", "core_org_units", ["parent_org_unit_id"]
    )
    op.create_index("ix_core_org_units_kind", "core_org_units", ["kind"])

    # -------------------------------------------------------------- core_staff
    op.create_table(
        "core_staff",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("employee_no", sa.String(), nullable=False),
        sa.Column("given_name", sa.String(), nullable=False),
        sa.Column("middle_name", sa.String(), nullable=True),
        sa.Column("surname", sa.String(), nullable=False),
        sa.Column("full_name", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("position_title", sa.String(), nullable=True),
        sa.Column("plantilla_item_no", sa.String(), nullable=True),
        sa.Column(
            "employment_status",
            postgresql.ENUM(name="core_employment_status", create_type=False),
            nullable=True,
        ),
        sa.Column("division_id", sa.BigInteger(), nullable=True),
        sa.Column("section_id", sa.BigInteger(), nullable=True),
        *_audit_soft_delete_cols(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_core_staff")),
        sa.ForeignKeyConstraint(
            ["division_id"],
            ["core_org_units.id"],
            name=op.f("fk_core_staff_division_id_core_org_units"),
        ),
        sa.ForeignKeyConstraint(
            ["section_id"],
            ["core_org_units.id"],
            name=op.f("fk_core_staff_section_id_core_org_units"),
        ),
    )
    op.create_index(
        "uq_core_staff_employee_no",
        "core_staff",
        ["employee_no"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "uq_core_staff_email",
        "core_staff",
        ["email"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND email IS NOT NULL"),
    )
    op.create_index("ix_core_staff_division_id", "core_staff", ["division_id"])
    op.create_index("ix_core_staff_section_id", "core_staff", ["section_id"])
    op.create_index("ix_core_staff_surname", "core_staff", ["surname"])

    # -------------------------------------------------------------- core_users
    op.create_table(
        "core_users",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=True),
        sa.Column(
            "must_change_password",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column(
            "password_changed_at", postgresql.TIMESTAMP(timezone=True), nullable=True
        ),
        sa.Column(
            "mfa_enabled", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column("mfa_secret", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "is_break_glass", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column(
            "auth_source",
            postgresql.ENUM(name="core_auth_source", create_type=False),
            server_default="local",
            nullable=False,
        ),
        sa.Column(
            "permissions_version",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("last_login_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("staff_id", sa.BigInteger(), nullable=True),
        *_audit_soft_delete_cols(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_core_users")),
        sa.ForeignKeyConstraint(
            ["staff_id"],
            ["core_staff.id"],
            name=op.f("fk_core_users_staff_id_core_staff"),
        ),
    )
    op.create_index(
        "uq_core_users_email",
        "core_users",
        ["email"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "uq_core_users_staff_id",
        "core_users",
        ["staff_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND staff_id IS NOT NULL"),
    )
    op.create_index("ix_core_users_is_active", "core_users", ["is_active"])
    op.create_index("ix_core_users_staff_id", "core_users", ["staff_id"])

    # -------------------------------------------------------------- core_roles
    op.create_table(
        "core_roles",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column(
            "is_system", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        *_audit_soft_delete_cols(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_core_roles")),
    )
    op.create_index(
        "uq_core_roles_code",
        "core_roles",
        ["code"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # -------------------------------------------------------- core_permissions
    op.create_table(
        "core_permissions",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        *_audit_soft_delete_cols(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_core_permissions")),
    )
    op.create_index(
        "uq_core_permissions_code",
        "core_permissions",
        ["code"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index("ix_core_permissions_category", "core_permissions", ["category"])

    # --------------------------------------------------- core_role_permissions
    op.create_table(
        "core_role_permissions",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("role_id", sa.BigInteger(), nullable=False),
        sa.Column("permission_id", sa.BigInteger(), nullable=False),
        *_audit_soft_delete_cols(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_core_role_permissions")),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["core_roles.id"],
            name=op.f("fk_core_role_permissions_role_id_core_roles"),
        ),
        sa.ForeignKeyConstraint(
            ["permission_id"],
            ["core_permissions.id"],
            name=op.f("fk_core_role_permissions_permission_id_core_permissions"),
        ),
    )
    op.create_index(
        "uq_core_role_permissions_role_id",
        "core_role_permissions",
        ["role_id", "permission_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_core_role_permissions_role_id", "core_role_permissions", ["role_id"]
    )
    op.create_index(
        "ix_core_role_permissions_permission_id",
        "core_role_permissions",
        ["permission_id"],
    )

    # ------------------------------------------------------- core_user_roles
    op.create_table(
        "core_user_roles",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("role_id", sa.BigInteger(), nullable=False),
        sa.Column("org_unit_id", sa.BigInteger(), nullable=True),
        sa.Column("valid_from", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("valid_to", postgresql.TIMESTAMP(timezone=True), nullable=True),
        *_audit_soft_delete_cols(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_core_user_roles")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["core_users.id"],
            name=op.f("fk_core_user_roles_user_id_core_users"),
        ),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["core_roles.id"],
            name=op.f("fk_core_user_roles_role_id_core_roles"),
        ),
        sa.ForeignKeyConstraint(
            ["org_unit_id"],
            ["core_org_units.id"],
            name=op.f("fk_core_user_roles_org_unit_id_core_org_units"),
        ),
    )
    # NULLS NOT DISTINCT (PG16): two (user, role, NULL) global grants must collide.
    op.create_index(
        "uq_core_user_roles_grant",
        "core_user_roles",
        ["user_id", "role_id", "org_unit_id"],
        unique=True,
        postgresql_nulls_not_distinct=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index("ix_core_user_roles_user_id", "core_user_roles", ["user_id"])
    op.create_index("ix_core_user_roles_role_id", "core_user_roles", ["role_id"])
    op.create_index(
        "ix_core_user_roles_org_unit_id", "core_user_roles", ["org_unit_id"]
    )

    # ----------------------------------------------------- core_login_attempts
    op.create_table(
        "core_login_attempts",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("attempted_identifier", sa.String(), nullable=False),
        sa.Column(
            "outcome",
            postgresql.ENUM(name="core_login_outcome", create_type=False),
            nullable=False,
        ),
        sa.Column("failure_reason", sa.String(), nullable=True),
        sa.Column("ip_address", sa.String(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("session_id_hash", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_core_login_attempts")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["core_users.id"],
            name=op.f("fk_core_login_attempts_user_id_core_users"),
        ),
    )
    op.create_index("ix_core_login_attempts_user_id", "core_login_attempts", ["user_id"])
    op.create_index(
        "ix_core_login_attempts_created_at", "core_login_attempts", ["created_at"]
    )
    op.create_index(
        "ix_core_login_attempts_outcome", "core_login_attempts", ["outcome"]
    )
    op.create_index(
        "ix_core_login_attempts_attempted_identifier",
        "core_login_attempts",
        ["attempted_identifier", "created_at"],
    )
    # Append-only: default privileges granted UPDATE to future tables — revoke it.
    op.execute("REVOKE UPDATE ON core_login_attempts FROM oc_app")


def downgrade() -> None:
    op.drop_table("core_login_attempts")
    op.drop_table("core_user_roles")
    op.drop_table("core_role_permissions")
    op.drop_table("core_permissions")
    op.drop_table("core_roles")
    op.drop_table("core_users")
    op.drop_table("core_staff")
    op.drop_table("core_org_units")
    postgresql.ENUM(name="core_login_outcome").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="core_auth_source").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="core_employment_status").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="core_org_unit_kind").drop(op.get_bind(), checkfirst=True)
