"""Stage B (Phase 2) QA gate: the identity schema + deferred-FK closure.

Proves migration 0010 turned every deferred ``*_by``/``actor_id``/org/tenant
column into a real FK to the right parent, that the sanctioned polymorphic /
generic-pointer columns stayed unconstrained, and the two highest-risk index
details (``NULLS NOT DISTINCT`` grant uniqueness, partial-unique email).
"""

import sqlalchemy as sa
from sqlalchemy import text

from tests.test_migrations import BUSINESS_TABLES, LOOKUP_TABLES

_BY_COLS = ("created_by", "updated_by", "deleted_by")

# Bespoke single-column deferred FKs → core_users (log/actor columns not covered
# by the AuditColsMixin closure) plus the structural user references.
_BESPOKE_USER_FKS = [
    ("core_audit_logs", "actor_id"),
    ("core_query_logs", "created_by"),
    ("core_notification_deliveries", "created_by"),
    ("core_report_lineages", "created_by"),
    ("core_report_lineages", "generated_by"),
    ("core_attachments", "disposed_by"),
    ("core_notifications", "recipient_user_id"),
    ("core_login_attempts", "user_id"),
    ("core_user_roles", "user_id"),
]


async def _foreign_keys(owner_session):
    def collect(sync_conn):
        insp = sa.inspect(sync_conn)
        return {t: insp.get_foreign_keys(t) for t in insp.get_table_names()}

    conn = await owner_session.connection()
    return await conn.run_sync(collect)


def _has_fk(fks, table, column, referred_table) -> bool:
    return any(
        fk["constrained_columns"] == [column] and fk["referred_table"] == referred_table
        for fk in fks.get(table, [])
    )


async def test_by_columns_fk_to_core_users(owner_session):
    """created_by / updated_by / deleted_by → core_users on every business/lookup
    table (the mixin closure), including core_users' own nullable self-reference."""
    fks = await _foreign_keys(owner_session)
    for table in BUSINESS_TABLES | LOOKUP_TABLES:
        for col in _BY_COLS:
            assert _has_fk(fks, table, col, "core_users"), (
                f"{table}.{col} -> core_users FK missing"
            )


async def test_bespoke_user_fks_closed(owner_session):
    fks = await _foreign_keys(owner_session)
    for table, col in _BESPOKE_USER_FKS:
        assert _has_fk(fks, table, col, "core_users"), (
            f"{table}.{col} -> core_users FK missing"
        )


async def test_org_and_tenant_fks_closed(owner_session):
    fks = await _foreign_keys(owner_session)
    assert _has_fk(fks, "core_activities", "division_id", "core_org_units")
    assert _has_fk(fks, "core_activities", "section_id", "core_org_units")
    assert _has_fk(fks, "core_staff", "division_id", "core_org_units")
    assert _has_fk(fks, "core_staff", "section_id", "core_org_units")
    assert _has_fk(fks, "core_org_units", "parent_org_unit_id", "core_org_units")
    assert _has_fk(fks, "core_users", "staff_id", "core_staff")
    assert _has_fk(
        fks, "core_compliance_deadlines", "tenant_id", "core_tenant_configs"
    )


async def test_sanctioned_polymorphic_columns_have_no_fk(owner_session):
    """The polymorphic (holder_kind, holder_id) and the generic row_pk pointer
    must NEVER gain an FK (database-standards §3)."""
    fks = await _foreign_keys(owner_session)
    for fk in fks.get("core_attachments", []):
        assert fk["constrained_columns"] != ["holder_id"], "holder_id must have no FK"
    for fk in fks.get("core_audit_logs", []):
        assert fk["constrained_columns"] != ["row_pk"], "row_pk must have no FK"


async def test_user_roles_grant_index_nulls_not_distinct(owner_session):
    """A NULLS DISTINCT index would let two (user, role, NULL) global grants both
    insert — the grant uniqueness MUST use NULLS NOT DISTINCT (PG16)."""
    value = (
        await owner_session.execute(
            text(
                "SELECT indnullsnotdistinct FROM pg_index "
                "WHERE indexrelid = 'uq_core_user_roles_grant'::regclass"
            )
        )
    ).scalar_one()
    assert value is True


async def test_users_email_partial_unique(owner_session):
    definition = (
        await owner_session.execute(
            text("SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_core_users_email'")
        )
    ).scalar_one_or_none()
    assert definition is not None
    assert "UNIQUE" in definition
    assert "deleted_at IS NULL" in definition
