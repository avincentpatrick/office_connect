"""R-1 schema invariants — the CA hard-block + the ref_no partial-unique guard."""

import secrets
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from office_connect.core.models import ReferenceSequence
from office_connect.core.soft_delete import soft_delete
from office_connect.modules.reimbursement.models import ReimbCashAdvance, ReimbClaim
from tests.reimbursement_helpers import make_cash_advance, make_claim, make_staff


async def test_ca_hard_block_one_open_per_claimant(app_session):
    """PD 1445 §89: a claimant may not hold two unliquidated cash advances."""
    staff = await make_staff(app_session)
    staff_id = staff.id  # capture before any rollback (rollback expires ORM state)
    await make_cash_advance(app_session, claimant_id=staff_id, status="open")
    await app_session.commit()

    # A second OPEN advance for the same claimant violates the DB hard-block.
    app_session.add(
        ReimbCashAdvance(claimant_id=staff_id, status="open", amount=Decimal("1000.00"))
    )
    with pytest.raises(IntegrityError):
        await app_session.flush()
    await app_session.rollback()

    # Settle the first, and a new advance is allowed.
    ca1 = (
        await app_session.execute(
            select(ReimbCashAdvance).where(ReimbCashAdvance.claimant_id == staff_id)
        )
    ).scalars().one()
    ca1.status = "settled"
    await app_session.commit()

    await make_cash_advance(app_session, claimant_id=staff_id, status="open")
    await app_session.commit()  # no error


async def test_ref_no_partial_unique(app_session):
    """Two LIVE claims cannot share a ref_no; a soft-deleted one frees the live slot
    (though the allocator never reissues the number in practice)."""
    staff = await make_staff(app_session)
    staff_id = staff.id
    ref_no = f"RB-2026-{secrets.token_hex(4)}"  # fresh per run (suite persists rows)
    await make_claim(app_session, claimant_id=staff_id, ref_no=ref_no)
    await app_session.commit()

    app_session.add(
        ReimbClaim(claimant_id=staff_id, kind="reimbursement", ref_no=ref_no)
    )
    with pytest.raises(IntegrityError):
        await app_session.flush()
    await app_session.rollback()

    # Soft-deleting the first lets the partial index accept the same ref_no again.
    c1 = (
        await app_session.execute(
            select(ReimbClaim).where(ReimbClaim.ref_no == ref_no)
        )
    ).scalars().one()
    soft_delete(c1)
    await app_session.commit()
    await make_claim(app_session, claimant_id=staff_id, ref_no=ref_no)
    await app_session.commit()  # no error


async def test_claim_carries_workflow_instance_fk_column(app_session):
    """The module → core link exists (the engine never references reimb)."""
    staff = await make_staff(app_session)
    claim = await make_claim(app_session, claimant_id=staff.id)
    assert claim.workflow_instance_id is None  # nullable until the chain starts (R-4-app)
    assert hasattr(claim, "workflow_instance_id")
    _ = ReferenceSequence  # imported for the schema smoke
