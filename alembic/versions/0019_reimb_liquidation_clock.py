"""reimb cash-advance liquidation clock

Revision ID: 0019
Revises: 0018
Create Date: 2026-08-04

Stage C Increment R-6-clock — the pinned 30-day liquidation deadline (COA
Circular 97-002) on ``reimb_cash_advances``.

``deadline_date`` is a stored computed snapshot rather than a derived read, for
three reasons: the daily reminder sweep range-queries it without loading the
effective config pack per row; the deadline a traveller was *told* must not
silently move when an admin edits ``liquidation.deadline`` or adds a holiday;
and ``reimb_claims.liquidation_deadline`` already sets that precedent.
``deadline_basis`` records WHICH rule produced it (``calendar`` per COA's text,
or ``working`` if DOH practice is later confirmed), pinned for the same reason.

Both nullable: an advance whose trip has not happened yet has no ``date_return``
and therefore no clock. Existing rows are backfilled from ``date_return`` on the
seeded calendar default — the only basis any live row was ever created under.
Reversible (down→up) + idempotent.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#: Mirrors the seeded ``liquidation.deadline`` default (COA Circular 97-002).
#: Inlined deliberately: a migration must reproduce byte-for-byte on a replay
#: years from now, so it may not read a config table a tenant can edit.
_DEFAULT_DAYS = 30


def upgrade() -> None:
    op.add_column(
        "reimb_cash_advances", sa.Column("deadline_date", sa.Date(), nullable=True)
    )
    op.add_column(
        "reimb_cash_advances", sa.Column("deadline_basis", sa.String(), nullable=True)
    )
    op.create_index(
        "ix_reimb_cash_advances_deadline_date",
        "reimb_cash_advances",
        ["deadline_date"],
    )
    # Backfill: every pre-existing row was created under the calendar default.
    op.execute(
        "UPDATE reimb_cash_advances "
        f"SET deadline_date = date_return + INTERVAL '{_DEFAULT_DAYS} days', "
        "    deadline_basis = 'calendar' "
        "WHERE date_return IS NOT NULL AND deadline_date IS NULL"
    )


def downgrade() -> None:
    op.drop_index("ix_reimb_cash_advances_deadline_date", "reimb_cash_advances")
    op.drop_column("reimb_cash_advances", "deadline_basis")
    op.drop_column("reimb_cash_advances", "deadline_date")
