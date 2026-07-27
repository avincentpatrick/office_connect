"""reimb 50-km attestation columns

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-27

Stage C Increment R-2-engine — two claimant-attested booleans on ``reimb_claims``
feeding the per-diem engine's 50-km gate (EO 77 s.2019: full DTE only beyond 50 km
from the official station; within 50 km without an overnight stay → transport fare
only, no DTE). Real columns rather than ``custom`` JSONB because checklist rules and
the engine branch on them (database-standards.md §11); see the module delta register.
Reversible (down→up) + idempotent.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "reimb_claims",
        sa.Column(
            "is_within_50km",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "reimb_claims",
        sa.Column(
            "overnight_stay",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("reimb_claims", "overnight_stay")
    op.drop_column("reimb_claims", "is_within_50km")
