"""reimb claim persisted other-expenses total

Revision ID: 0016
Revises: 0015
Create Date: 2026-07-30

Stage C Increment R-2-wizard — ``reimb_claims.other_total`` numeric(12,2). Before
this column, "other expenses" existed only as a call parameter on
``compute_claim_totals``/``submit_claim``, so a resubmit-after-return recomputed
without it and silently reset "other" to zero. The column is now the single
source of truth (compute reads it; an explicit parameter persists to it first).
Existing computed snapshots are converged from ``totals->>'other'`` so live
claims keep their value. Itemized expense lines (spec §9.3) arrive with the R-3
checklist engine. Reversible (down→up) + idempotent.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "reimb_claims",
        sa.Column(
            "other_total",
            sa.Numeric(12, 2),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    # Converge pre-existing computed snapshots onto the new source-of-truth column.
    op.execute(
        "UPDATE reimb_claims SET other_total = (totals->>'other')::numeric(12,2) "
        "WHERE totals ? 'other' AND (totals->>'other') <> ''"
    )


def downgrade() -> None:
    op.drop_column("reimb_claims", "other_total")
