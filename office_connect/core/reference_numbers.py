"""Reference-number allocation — core-service #5 (master-plan §1.1 #5).

`allocate_reference_number(session, scope="RB", year=2026) -> "RB-2026-0001"`. One
allocator for every `XX-YYYY-NNNN` series (reimbursement first; DTWIS/QMS/supply later).
The `(scope, year)` counter row is locked `FOR UPDATE` and incremented in the caller's
transaction, so concurrent allocations serialize and never collide; numbers reset yearly
and are **never reused** (the counter only advances — voids/soft-deletes retain theirs).

Row creation for a brand-new `(scope, year)` is guarded by the table's unique index; the
extremely rare first-of-year insert race surfaces as an `IntegrityError` the caller
retries (office scale — a handful of new series per year).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.models import ReferenceSequence
from office_connect.core.time import utc_now

_PAD = 4  # NNNN — widens automatically past 9999 within a year


async def allocate_reference_number(
    session: AsyncSession, *, scope: str, year: int | None = None
) -> str:
    """Allocate and return the next `"{scope}-{year}-{NNNN}"` for `(scope, year)`.

    Adds/updates the counter in the caller's session and flushes; the caller owns the
    commit (so the number and the business row it labels commit atomically)."""
    year = year or utc_now().year
    row = (
        await session.execute(
            select(ReferenceSequence)
            .where(
                ReferenceSequence.scope == scope,
                ReferenceSequence.year == year,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        row = ReferenceSequence(scope=scope, year=year, last_value=0)
        session.add(row)
        await session.flush()  # may raise IntegrityError on the first-of-year race
    row.last_value += 1
    await session.flush()
    return f"{scope}-{year:04d}-{row.last_value:0{_PAD}d}"
