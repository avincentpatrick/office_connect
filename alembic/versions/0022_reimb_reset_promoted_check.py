"""reimb: reset promoted_check — nothing ships promoted

Revision ID: 0022
Revises: 0021
Create Date: 2026-08-06

Stage C Increment R-8. A **data-only** migration: no column is added, dropped or
retyped. What changes is what an existing column MEANS, and that is exactly the
kind of change a migration exists to make honest.

``reimb_return_reason_catalogs.promoted_check`` shipped at R-1 (spec §5.6) and
has never been read by anything. Its seed carried ``True`` on three rows —
``MISSING_OR``, ``PER_DIEM_CALC``, ``FARE_CLASS`` — under the model's original
gloss, *"if true, this reason CAN be promoted to a pre-check"*. R-8 makes the
column mean what spec §11 needs it to mean: **this reason IS promoted**, i.e. a
warning is shown to every claimant at wizard step 5.

Under the new meaning those three rows are three warnings nobody chose, live on
the day the feature ships. That inverts the fail-safe direction an advisory
must take. Everywhere else in this codebase the safe answer is to block (the
packet gate) or to flag (an auto-check); here it is the opposite — **when in
doubt, do not warn** — because a warning that appeared without an author is a
warning nobody can explain, defend or retire, and it spends the credibility of
every honest warning beside it. Spec §14 grades R-8 on "promotion creates a
working warning", which presupposes that an unpromoted reason creates none.

The seed stops asserting the column at all in the same increment, and that is
the more important half: ``apply_dataset`` writes only the keys a row dict
contains, so a ``promoted_check`` left in the seed would be re-asserted on every
run — **silently demoting every reason an Admin Officer had promoted**, on the
next deployment, leaving nothing behind but a warning that stopped appearing.
With the key gone the column keeps its ``server_default false`` at insert and is
owned by exactly one writer thereafter
(``services/insights.py::set_promoted``).

Reversible in the only sense a data migration can be: ``downgrade`` restores
``True`` on precisely the three seeded codes, which is the state ``0021`` left
behind. It cannot restore promotions made after this ran — those are the new
regime's data, and a downgrade that guessed at them would invent authorship.
Both directions are idempotent and neither touches a row that is already right.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#: The three codes the R-1 seed shipped with ``promoted_check = true``.
_SEEDED_TRUE = ("MISSING_OR", "PER_DIEM_CALC", "FARE_CLASS")


def upgrade() -> None:
    op.execute(
        "UPDATE reimb_return_reason_catalogs "
        "SET promoted_check = false "
        "WHERE promoted_check IS DISTINCT FROM false"
    )


def downgrade() -> None:
    codes = ", ".join(f"'{code}'" for code in _SEEDED_TRUE)
    op.execute(
        "UPDATE reimb_return_reason_catalogs "
        "SET promoted_check = true "
        f"WHERE code IN ({codes}) AND promoted_check IS DISTINCT FROM true"
    )
