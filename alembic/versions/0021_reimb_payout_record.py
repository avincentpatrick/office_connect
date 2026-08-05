"""reimb payout record — what FMS paid, against what reference, and when

Revision ID: 0021
Revises: 0020
Create Date: 2026-08-05

Stage C Increment R-7-events. Spec §6.1 row 8 says ``Paid / Closed`` is
"terminal (admin records payout ref)" — and until this migration there was
nowhere to record one. ``handed_to_fms --approve--> paid_closed`` was a bare
verb: the claim closed and the system held no evidence of what FMS actually
paid, against what reference, or on what date. These three columns are what
make closing a claim MEAN something, and they are the reimbursement chain's
exact analogue of the settlement record ``0020`` put on the cash advance.

``payout_ref`` is what FMS hands back (an ADA/LDDAP reference, a check number —
the field is deliberately unopinionated, because the resident COA auditor has
not been asked which of those DOH BLHSD's FMS actually quotes). It is
**NOT unique and gets no unique index**: one LDDAP-ADA legitimately pays many
disbursement vouchers at once, so two claims sharing a reference is normal
government practice, not a duplicate.

``paid_on`` is the DATE FMS paid — the fact an auditor traces from the claim
into the cash book. Deliberately a date and not a ``paid_at`` timestamp: the
moment the row was written is already recorded twice over, by ``updated_at`` and
by the ``reimb_status_histories`` row the transition appends, and a timestamp
here would invite the two to be read as the same fact when one is "when the
money moved" and the other is "when somebody typed it in".

``paid_by`` is a real column rather than an inference from ``updated_by`` for
exactly the reason ``0020``'s ``settled_by`` is one (rule 5 — ownership columns
AND the hash-chained audit log): who closed a financial record is a fact OF the
record, not a trace left behind by whoever last touched the row.

All three are nullable and nothing is backfilled: a claim nobody has paid has no
payout. The NOT-NULL-ness that matters is enforced where it can carry a decent
sentence — ``services/external.py::record_payout`` refuses a blank reference, and
``lifecycle._assert_payout_recorded`` refuses the bare ``approve`` that would
skip it.

Reversible (down→up) + idempotent.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "reimb_claims", sa.Column("payout_ref", sa.String(), nullable=True)
    )
    op.add_column("reimb_claims", sa.Column("paid_on", sa.Date(), nullable=True))
    op.add_column(
        "reimb_claims", sa.Column("paid_by", sa.BigInteger(), nullable=True)
    )
    op.create_foreign_key(
        op.f("fk_reimb_claims_paid_by_core_users"),
        "reimb_claims",
        "core_users",
        ["paid_by"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_reimb_claims_paid_by_core_users"), "reimb_claims", type_="foreignkey"
    )
    op.drop_column("reimb_claims", "paid_by")
    op.drop_column("reimb_claims", "paid_on")
    op.drop_column("reimb_claims", "payout_ref")
