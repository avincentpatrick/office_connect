"""reimb checklist engine — item uniqueness, circular pinning, retention fix

Revision ID: 0017
Revises: 0016
Create Date: 2026-08-03

Stage C Increment R-3 (the checklist engine + uploads). Three changes, each
justified by an invariant or a defect — no new table, no new enum value:

1. **Partial unique index on ``reimb_checklist_items (claim_id, catalog_id)``**
   — at most one LIVE item per claim per catalog row, the invariant the
   reconciliation algorithm assumes. Two concurrent writers would otherwise
   split a claimant's evidence across two rows. The claim's ``SELECT … FOR
   UPDATE`` lock is the real race fix; this is the DB belt behind it, exactly as
   ``0015`` is for claim↔instance.

2. **``reimb_checklist_items.circular_version``** — master-plan §1.1 core-service
   #7 requires "catalog versions pinned to the issuing circular revision", but
   the seed framework upserts catalog rows IN PLACE by natural key, so a future
   COA revision would retroactively rewrite what a historical claim's item
   meant. Snapshotting at materialization is the fix and cannot be backfilled
   later.

3. **``reimb_attachments.retention_class`` default → ``financial_dv_10y``** —
   BUG FIX. The shipped default ``financial_10yr`` is not a key of
   ``core/attachments/retention.py::RETENTION_CLASSES`` (which spells it
   ``financial_dv_10y``), so ``retain_until()`` fell through its unknown-class
   fail-safe and returned ``None`` — meaning every claim attachment would be
   permanently non-disposable and mislabeled in the disposal-eligibility report.
   R-3 creates the first rows this table has ever held, so the fix is free now
   and a data migration later.

Reversible (down→up) + idempotent.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "uq_reimb_checklist_items_claim_catalog",
        "reimb_checklist_items",
        ["claim_id", "catalog_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.add_column(
        "reimb_checklist_items",
        sa.Column("circular_version", sa.String(), nullable=True),
    )
    op.alter_column(
        "reimb_attachments",
        "retention_class",
        server_default="financial_dv_10y",
        existing_type=sa.String(),
        existing_nullable=False,
    )
    op.execute(
        "UPDATE reimb_attachments SET retention_class = 'financial_dv_10y' "
        "WHERE retention_class = 'financial_10yr'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE reimb_attachments SET retention_class = 'financial_10yr' "
        "WHERE retention_class = 'financial_dv_10y'"
    )
    op.alter_column(
        "reimb_attachments",
        "retention_class",
        server_default="financial_10yr",
        existing_type=sa.String(),
        existing_nullable=False,
    )
    op.drop_column("reimb_checklist_items", "circular_version")
    op.drop_index(
        "uq_reimb_checklist_items_claim_catalog",
        table_name="reimb_checklist_items",
    )
