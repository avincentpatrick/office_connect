"""QA gates: migration idempotency + mandatory column sets (rules 5–7).

Verifies database-standards.md §6 table classes against the live schema.
"""

import subprocess

import sqlalchemy as sa

from tests.conftest import REPO_ROOT

BUSINESS_TABLES = {
    "core_tenant_configs",
    "core_activities",
    "core_activity_tag_assignments",
    "core_attachments",
    "core_notifications",
    # Stage B (Phase 2) identity
    "core_staff",
    "core_users",
    "core_role_permissions",
    "core_user_roles",
    # Stage C — shared workflow engine
    "core_workflow_definitions",
    "core_workflow_definition_versions",
    "core_workflow_states",
    "core_workflow_transitions",
    "core_workflow_instances",
    "core_workflow_steps",
    "core_workflow_delegations",
}
LOOKUP_TABLES = {
    "core_feature_flags",
    "core_activity_tags",
    "core_pap_codes",
    "core_object_codes",
    "core_holidays",
    "core_compliance_deadlines",
    # Stage B (Phase 2) identity
    "core_org_units",
    "core_roles",
    "core_permissions",
}
APPEND_ONLY_TABLES = {
    "core_audit_logs",
    "core_query_logs",
    "core_notification_deliveries",
    "core_report_lineages",
    "core_login_attempts",
    # Stage C — append-only, audited decision log
    "core_workflow_events",
}
AUDIT_COLS = {"created_at", "created_by", "updated_at", "updated_by"}
SOFT_DELETE_COLS = {"deleted_at", "deleted_by"}


def test_upgrade_head_idempotent():
    """Running `alembic upgrade head` twice must both succeed (QA gate)."""
    for attempt in (1, 2):
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        assert result.returncode == 0, f"attempt {attempt}: {result.stderr}"


async def test_mandatory_column_sets(owner_session):
    def collect_columns(sync_conn):
        inspector = sa.inspect(sync_conn)
        return {
            table: {col["name"] for col in inspector.get_columns(table)}
            for table in inspector.get_table_names()
        }

    conn = await owner_session.connection()
    columns = await conn.run_sync(collect_columns)

    for table in BUSINESS_TABLES | LOOKUP_TABLES | APPEND_ONLY_TABLES:
        assert table in columns, f"spine table {table} missing"

    for table in BUSINESS_TABLES | LOOKUP_TABLES:
        missing = (AUDIT_COLS | SOFT_DELETE_COLS) - columns[table]
        assert not missing, f"{table} missing mandatory columns {missing}"

    for table in LOOKUP_TABLES:
        assert "is_active" in columns[table], f"{table} missing is_active"

    for table in APPEND_ONLY_TABLES:
        assert "created_at" in columns[table]
        forbidden = {"updated_at", "updated_by", *SOFT_DELETE_COLS} & columns[table]
        assert not forbidden, f"append-only {table} must not have {forbidden}"
