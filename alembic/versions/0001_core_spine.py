"""core spine — tenant configs, feature flags, audit chain, query log, activities

Revision ID: 0001
Revises:
Create Date: 2026-07-22

Creates the Phase-0 spine (docs/modules/foundation.md §4) with the full
mandatory column sets (database-standards.md §6), the runtime role ``oc_app``
(no DELETE anywhere; no UPDATE on append-only tables), and neutral seeds.

Notes:
- Seeds run as the owner role (oc_dev) and sit OUTSIDE the audit chain — the
  chain's genesis is the first app write.
- Default privileges grant SELECT/INSERT/UPDATE on FUTURE tables to oc_app;
  later APPEND-ONLY tables must explicitly REVOKE UPDATE in their migration.
"""

import os
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MUTABLE_TABLES = ("core_tenant_configs", "core_feature_flags", "core_activities")
APPEND_ONLY_TABLES = ("core_audit_logs", "core_query_logs")


def _audit_soft_delete_cols() -> list[sa.Column]:
    """Mandatory business-table columns (database-standards.md §6)."""
    return [
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("created_by", sa.BigInteger(), nullable=True),  # FK → core_users (Phase 2)
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
    # ------------------------------------------------------------- tables
    op.create_table(
        "core_tenant_configs",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("short_name", sa.String(), nullable=False),
        sa.Column(
            "timezone", sa.String(), server_default="Asia/Manila", nullable=False
        ),
        sa.Column(
            "branding",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        *_audit_soft_delete_cols(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_core_tenant_configs")),
    )

    op.create_table(
        "core_feature_flags",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        *_audit_soft_delete_cols(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_core_feature_flags")),
    )
    # Partial unique: a soft-deleted flag never blocks re-creating its key (§8).
    op.create_index(
        "uq_core_feature_flags_key",
        "core_feature_flags",
        ["key"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "core_audit_logs",
        # GENERATED ALWAYS — nobody may insert an explicit id into the chain.
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        # App-set (inside the hash) — deliberately NO server default.
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("actor_id", sa.BigInteger(), nullable=True),  # FK → core_users (Phase 2)
        sa.Column("request_id", sa.String(), nullable=True),
        sa.Column("table_name", sa.String(), nullable=False),
        sa.Column("row_pk", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("old_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("new_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("prev_hash", postgresql.CHAR(64), nullable=False),
        sa.Column("row_hash", postgresql.CHAR(64), nullable=False),
        sa.CheckConstraint(
            "action IN ('insert', 'update', 'soft_delete')",
            name=op.f("ck_core_audit_logs_action"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_core_audit_logs")),
        sa.UniqueConstraint("row_hash", name=op.f("uq_core_audit_logs_row_hash")),
    )
    op.create_index(
        "ix_core_audit_logs_table_name_row_pk",
        "core_audit_logs",
        ["table_name", "row_pk"],
    )
    op.create_index("ix_core_audit_logs_created_at", "core_audit_logs", ["created_at"])

    op.create_table(
        "core_query_logs",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("created_by", sa.BigInteger(), nullable=True),  # FK → core_users (Phase 2)
        sa.Column("module", sa.String(), nullable=False),
        sa.Column("resource", sa.String(), nullable=False),
        sa.Column("action", sa.String(), server_default="read", nullable=False),
        sa.Column("detail", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("request_id", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_core_query_logs")),
    )
    op.create_index("ix_core_query_logs_created_at", "core_query_logs", ["created_at"])
    op.create_index("ix_core_query_logs_created_by", "core_query_logs", ["created_by"])

    activity_status = postgresql.ENUM(
        "planned", "ongoing", "done", "cancelled", name="core_activity_status"
    )
    activity_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "core_activities",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("ppa_code", sa.String(), nullable=True),
        sa.Column("division_id", sa.BigInteger(), nullable=True),  # FK → org units (Phase 2)
        sa.Column("section_id", sa.BigInteger(), nullable=True),  # FK → org units (Phase 2)
        sa.Column("date_start", sa.Date(), nullable=False),
        sa.Column("date_end", sa.Date(), nullable=True),
        sa.Column("venue", sa.String(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(name="core_activity_status", create_type=False),
            server_default="planned",
            nullable=False,
        ),
        sa.Column(
            "custom",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        *_audit_soft_delete_cols(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_core_activities")),
    )
    op.create_index("ix_core_activities_status", "core_activities", ["status"])
    op.create_index("ix_core_activities_date_start", "core_activities", ["date_start"])
    op.create_index("ix_core_activities_ppa_code", "core_activities", ["ppa_code"])

    # ------------------------------------------- runtime role + grants (§8)
    # oc_app: SELECT/INSERT/UPDATE on mutable tables, SELECT/INSERT only on
    # append-only tables, NO DELETE / NO TRUNCATE anywhere.
    #
    # The password is set by a plain ALTER ROLE (single-quote escaping is
    # complete there — inside a DO $$ body a password containing "$$" would
    # terminate the dollar-quoting). NOTE: changing OC_APP_PASSWORD after this
    # migration has run requires a manual ALTER ROLE (or a fresh DB) — the
    # migration never re-executes. Offline `--sql` mode writes the password
    # into the generated script — do not use --sql output for real
    # environments without redacting it.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'oc_app') THEN
                CREATE ROLE oc_app LOGIN;
            END IF;
        END
        $$;
        """
    )
    oc_app_password = os.environ.get("OC_APP_PASSWORD", "oc_app_pw").replace("'", "''")
    op.execute(f"ALTER ROLE oc_app WITH LOGIN PASSWORD '{oc_app_password}'")
    op.execute("GRANT USAGE ON SCHEMA public TO oc_app")
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE ON {', '.join(MUTABLE_TABLES)} TO oc_app"
    )
    op.execute(f"GRANT SELECT, INSERT ON {', '.join(APPEND_ONLY_TABLES)} TO oc_app")
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO oc_app")
    # Future tables/sequences created by the owner inherit these; append-only
    # tables must REVOKE UPDATE explicitly in their own migration.
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT SELECT, INSERT, UPDATE ON TABLES TO oc_app"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT USAGE, SELECT ON SEQUENCES TO oc_app"
    )

    # ------------------------------------------------------------- seeds
    # Outside the audit chain (owner-role write; chain genesis = first app write).
    op.execute(
        "INSERT INTO core_tenant_configs (name, short_name) "
        "VALUES ('Office-Connect', 'OC')"
    )
    op.execute(
        """
        INSERT INTO core_feature_flags (key, enabled, description) VALUES
            ('module.reimbursement', false, 'Local Travel Reimbursement module'),
            ('module.css_is', false, 'CSS-IS client satisfaction module'),
            ('module.dmwis', false, 'DMWIS document management module')
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "REVOKE SELECT, INSERT, UPDATE ON TABLES FROM oc_app"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "REVOKE USAGE, SELECT ON SEQUENCES FROM oc_app"
    )
    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM oc_app")
    op.execute("REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM oc_app")
    op.execute("REVOKE USAGE ON SCHEMA public FROM oc_app")
    # Roles are cluster-wide; if oc_app still holds privileges in another
    # database of the same cluster the DROP would fail — leave it in place
    # with a notice rather than aborting the downgrade.
    op.execute(
        """
        DO $$
        BEGIN
            DROP ROLE IF EXISTS oc_app;
        EXCEPTION WHEN dependent_objects_still_exist THEN
            RAISE NOTICE
                'oc_app keeps privileges in another database; role not dropped';
        END
        $$;
        """
    )

    op.drop_table("core_activities")
    postgresql.ENUM(name="core_activity_status").drop(op.get_bind(), checkfirst=True)
    op.drop_table("core_query_logs")
    op.drop_table("core_audit_logs")
    op.drop_index("uq_core_feature_flags_key", table_name="core_feature_flags")
    op.drop_table("core_feature_flags")
    op.drop_table("core_tenant_configs")
