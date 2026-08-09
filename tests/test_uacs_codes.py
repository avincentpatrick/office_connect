"""Increment 4 Group B — UACS/PREXC codes: per-FY tree, effective-dated, no-reuse.

⚠ ``core_pap_codes`` and ``core_object_codes`` are SEEDED reference tables, so
every row here goes in through ``owned_row`` and comes back out. Tokenized
natural keys keep a run from colliding with itself; they do nothing about the
row still being there next month (``seed_addition_guard``, conftest).
"""

import uuid
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from office_connect.core.models import ObjectCode, PapCode
from office_connect.core.soft_delete import soft_delete

from tests.conftest import owned_row


def _tok() -> str:
    return uuid.uuid4().hex[:10]


async def test_pap_tree_parent_child(app_session):
    root = PapCode(
        fiscal_year=2026,
        uacs_code=f"root-{_tok()}",
        level="cost_structure",
        title="General Administration and Support",
        effective_from=date(2026, 1, 1),
    )
    async with owned_row(app_session, root):
        child = PapCode(
            fiscal_year=2026,
            uacs_code=f"child-{_tok()}",
            level="program",
            parent_id=root.id,
            title="General Management and Supervision",
            effective_from=date(2026, 1, 1),
        )
        async with owned_row(app_session, child):
            loaded = (
                await app_session.execute(
                    select(PapCode).where(PapCode.id == child.id)
                )
            ).scalar_one()
            assert loaded.parent_id == root.id


async def test_pap_code_unique_per_fiscal_year(app_session):
    code = f"oo-{_tok()}"
    a = PapCode(
        fiscal_year=2027,
        uacs_code=code,
        level="oo",
        title="Outcome",
        effective_from=date(2027, 1, 1),
    )
    async with owned_row(app_session, a):
        dup = PapCode(
            fiscal_year=2027,
            uacs_code=code,
            level="oo",
            title="Dup",
            effective_from=date(2027, 1, 1),
        )
        app_session.add(dup)
        with pytest.raises(IntegrityError):
            await app_session.commit()
        # The rollback both clears the failed insert and expires `a` — which is
        # why `owned_row` re-fetches by PK rather than reusing the instance.
        await app_session.rollback()


async def test_object_code_effective_dated_revision(app_session):
    """Same UACS object code, a new effective date = a new row (never edit in place)."""
    code = f"5-02-01-{_tok()}"
    v1 = ObjectCode(
        uacs_object_code=code,
        title="Traveling Expenses - Local",
        effective_from=date(2020, 1, 1),
        effective_to=date(2025, 12, 31),
    )
    v2 = ObjectCode(
        uacs_object_code=code,
        title="Traveling Expenses - Local",
        effective_from=date(2026, 1, 1),
    )
    async with owned_row(app_session, v1), owned_row(app_session, v2):
        assert v1.id != v2.id

        # Same (code, effective_from) among live rows is rejected.
        dup = ObjectCode(
            uacs_object_code=code,
            title="Dup",
            effective_from=date(2026, 1, 1),
        )
        app_session.add(dup)
        with pytest.raises(IntegrityError):
            await app_session.commit()
        await app_session.rollback()


async def test_soft_deleted_object_code_frees_key(app_session):
    code = f"5-02-03-{_tok()}"
    row = ObjectCode(
        uacs_object_code=code,
        title="Other Supplies",
        effective_from=date(2026, 1, 1),
    )
    app_session.add(row)
    await app_session.commit()
    soft_delete(row)
    await app_session.commit()

    revived = ObjectCode(
        uacs_object_code=code,
        title="Other Supplies (re-added)",
        effective_from=date(2026, 1, 1),
    )
    # `row` needs no undo — the test soft-deletes it as its whole point. Only
    # the revived row would survive the run.
    async with owned_row(app_session, revived):
        assert revived.id != row.id
