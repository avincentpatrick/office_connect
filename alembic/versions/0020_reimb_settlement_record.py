"""reimb settlement record + the spawn link + the one-liquidation belt

Revision ID: 0020
Revises: 0019
Create Date: 2026-08-04

Stage C Increment R-6-liq-settle — the MONEY half of the liquidation. Three
things in one migration because all three are the same fact: a liquidation has
exactly one answer, and that answer is money.

``reimb_cash_advances`` gains the settlement RECORD. ``settled_at`` has existed
since ``0013`` and was never once written; these are the columns that make
writing it mean something. ``settlement_mode`` (``refund`` | ``exact`` |
``over_advance``) is a plain varchar with its legal set in code, following the
``deadline_basis`` precedent from ``0019``: the set is decided by
``services/per_diem.py::settle``, not by DDL, and a PG enum would demand a
migration the day a fourth outcome is confirmed with the resident COA auditor.
``settled_by`` is a real column rather than an inference from ``updated_by`` for
exactly the reason ``settled_at`` is one rather than an inference from
``updated_at`` (rule 5 — ownership columns AND the hash-chained audit log): who
closed a financial record is a fact OF the record, not a trace left behind by
whoever last touched the row.

``reimb_claims.spawned_from_claim_id`` is spec §6.2's "Reimbursement Due"
side-step made durable — the reimbursement of the difference points back at the
liquidation that produced it, so neither document can be read without the other.
Its partial-unique index means ONE live spawn per liquidation; ``cancelled`` is
excluded, the same exclusion ``liquidation.LIVE_STATUSES`` already makes, so a
mistaken spawn can be cancelled and re-taken.

``uq_reimb_claims_live_liquidation_per_advance`` is the DB belt R-6-liq-chain
deferred. ``services/liquidation.py::start_liquidation`` serializes on a
``SELECT … FOR UPDATE`` of the advance (the real race fix); this is the
guarantee behind it, exactly as ``0015`` followed R-4-app's row lock. It is
created with NO repair pass: a pre-existing duplicate makes this migration fail
loudly, which is correct — which of two liquidations is the real one is a
question for the Admin Officer, not something a migration may decide.

``IS DISTINCT FROM 'cancelled'`` rather than ``<> 'cancelled'`` because
``reimb_claims.status`` is nullable: ``<>`` is NULL-for-NULL and would drop every
un-stamped row out of the index — precisely the row a duplicate would hide
behind. The service checks use ``status IN (live states)`` instead, which
excludes NULL, so the two disagree by design and ``start_liquidation`` catches
the resulting ``IntegrityError`` and re-raises the named 409.

All six columns are nullable and nothing is backfilled: an unsettled advance has
no settlement, and a claim nobody spawned has no parent.
Reversible (down→up) + idempotent.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#: The live-claim predicate, shared by both new partial-unique indexes. Mirrored
#: verbatim in ``models/claim.py`` — the two must agree or ``alembic check``
#: reports drift on every run.
_LIVE = "status IS DISTINCT FROM 'cancelled' AND deleted_at IS NULL"
_SPAWN_WHERE = f"spawned_from_claim_id IS NOT NULL AND {_LIVE}"
_LIQUIDATION_WHERE = (
    f"kind = 'liquidation' AND cash_advance_id IS NOT NULL AND {_LIVE}"
)


def upgrade() -> None:
    # --- the settlement record, on the advance ----------------------------
    op.add_column(
        "reimb_cash_advances", sa.Column("settlement_mode", sa.String(), nullable=True)
    )
    op.add_column(
        "reimb_cash_advances", sa.Column("refund_or_no", sa.String(), nullable=True)
    )
    op.add_column(
        "reimb_cash_advances", sa.Column("refund_or_date", sa.Date(), nullable=True)
    )
    op.add_column(
        "reimb_cash_advances",
        sa.Column("refund_amount", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column(
        "reimb_cash_advances", sa.Column("settled_by", sa.BigInteger(), nullable=True)
    )
    op.create_foreign_key(
        op.f("fk_reimb_cash_advances_settled_by_core_users"),
        "reimb_cash_advances",
        "core_users",
        ["settled_by"],
        ["id"],
    )

    # --- the spawn link, on the claim -------------------------------------
    op.add_column(
        "reimb_claims",
        sa.Column("spawned_from_claim_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_reimb_claims_spawned_from_claim_id_reimb_claims"),
        "reimb_claims",
        "reimb_claims",
        ["spawned_from_claim_id"],
        ["id"],
    )
    op.create_index(
        "ix_reimb_claims_spawned_from_claim_id",
        "reimb_claims",
        ["spawned_from_claim_id"],
    )
    op.create_index(
        "uq_reimb_claims_spawn_per_liquidation",
        "reimb_claims",
        ["spawned_from_claim_id"],
        unique=True,
        postgresql_where=sa.text(_SPAWN_WHERE),
    )

    # --- the belt R-6-liq-chain deferred ----------------------------------
    op.create_index(
        "uq_reimb_claims_live_liquidation_per_advance",
        "reimb_claims",
        ["cash_advance_id"],
        unique=True,
        postgresql_where=sa.text(_LIQUIDATION_WHERE),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_reimb_claims_live_liquidation_per_advance",
        table_name="reimb_claims",
        postgresql_where=sa.text(_LIQUIDATION_WHERE),
    )
    op.drop_index(
        "uq_reimb_claims_spawn_per_liquidation",
        table_name="reimb_claims",
        postgresql_where=sa.text(_SPAWN_WHERE),
    )
    op.drop_index(
        "ix_reimb_claims_spawned_from_claim_id", table_name="reimb_claims"
    )
    op.drop_constraint(
        op.f("fk_reimb_claims_spawned_from_claim_id_reimb_claims"),
        "reimb_claims",
        type_="foreignkey",
    )
    op.drop_column("reimb_claims", "spawned_from_claim_id")
    op.drop_constraint(
        op.f("fk_reimb_cash_advances_settled_by_core_users"),
        "reimb_cash_advances",
        type_="foreignkey",
    )
    op.drop_column("reimb_cash_advances", "settled_by")
    op.drop_column("reimb_cash_advances", "refund_amount")
    op.drop_column("reimb_cash_advances", "refund_or_date")
    op.drop_column("reimb_cash_advances", "refund_or_no")
    op.drop_column("reimb_cash_advances", "settlement_mode")
