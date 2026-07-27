"""Shared builders for the reimbursement (R-1) tests."""

from __future__ import annotations

import secrets
from decimal import Decimal

from office_connect.core.models import Staff
from office_connect.modules.reimbursement.models import ReimbCashAdvance, ReimbClaim


async def make_staff(session, *, employment_status: str = "permanent", **kw) -> Staff:
    n = secrets.token_hex(4)
    staff = Staff(
        employee_no=f"E-{n}",
        given_name="Test",
        surname="Claimant",
        full_name=f"Test Claimant {n}",
        employment_status=employment_status,
        **kw,
    )
    session.add(staff)
    await session.flush()
    return staff


async def make_cash_advance(
    session, *, claimant_id: int, status: str = "open", amount: str = "5000.00", **kw
) -> ReimbCashAdvance:
    ca = ReimbCashAdvance(
        claimant_id=claimant_id, status=status, amount=Decimal(amount), **kw
    )
    session.add(ca)
    await session.flush()
    return ca


async def make_claim(
    session, *, claimant_id: int, kind: str = "reimbursement", ref_no: str | None = None,
    **kw,
) -> ReimbClaim:
    claim = ReimbClaim(claimant_id=claimant_id, kind=kind, ref_no=ref_no, **kw)
    session.add(claim)
    await session.flush()
    return claim
