"""Index reimb_claims.date_depart for the calendar's travel window.

Stage D-2. The `reimb.travel` calendar source filters on a date window
(`date_depart <= end AND coalesce(date_return, date_depart) >= start`), and
`date_depart` is the leading, sargable half of that predicate — without an index
every calendar request is a sequential scan of `reimb_claims`.

Its siblings already had theirs: `ix_core_activities_date_start` (migration
0001) and `ix_reimb_cash_advances_deadline_date` (0019). This one was simply
missing, because until now nothing queried claims BY TRIP DATE — the queue and
the board both order on `holder_since`.

No tables, no columns, no data. Down drops the index.

Revision ID: 0024
Revises: 0023
"""

from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_reimb_claims_date_depart", "reimb_claims", ["date_depart"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_reimb_claims_date_depart", table_name="reimb_claims")
