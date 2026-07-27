"""Shared builders for the reimbursement (R-1/R-2) tests."""

from __future__ import annotations

import secrets
from datetime import date
from decimal import Decimal

from office_connect.core.models import Staff
from office_connect.modules.reimbursement.models import (
    ReimbCashAdvance,
    ReimbClaim,
    ReimbItineraryLeg,
)


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


async def make_leg(
    session, *, claim_id: int, seq: int = 1, leg_date: date | None = None,
    fare: str | None = None, **kw,
) -> ReimbItineraryLeg:
    leg = ReimbItineraryLeg(
        claim_id=claim_id,
        seq=seq,
        leg_date=leg_date,
        fare=Decimal(fare) if fare is not None else None,
        **kw,
    )
    session.add(leg)
    await session.flush()
    return leg
