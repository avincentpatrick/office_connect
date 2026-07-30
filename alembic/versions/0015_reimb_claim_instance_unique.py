"""reimb claim ↔ workflow instance one-to-one belt

Revision ID: 0015
Revises: 0014
Create Date: 2026-07-29

Stage C Increment R-4-app — partial unique index on
``reimb_claims.workflow_instance_id``. The submit service serializes concurrent
submits with a ``SELECT … FOR UPDATE`` on the claim row (the real race fix);
this index is the DB-level belt behind it, guaranteeing a workflow instance can
never be wired to two claims (project style: invariants enforced in the schema,
cf. the open-cash-advance hard-block in ``0013``). All existing rows are NULL,
so creation is trivially safe. Reversible (down→up) + idempotent.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "uq_reimb_claims_workflow_instance_id",
        "reimb_claims",
        ["workflow_instance_id"],
        unique=True,
        postgresql_where=sa.text("workflow_instance_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_reimb_claims_workflow_instance_id",
        table_name="reimb_claims",
        postgresql_where=sa.text("workflow_instance_id IS NOT NULL"),
    )
