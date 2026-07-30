"""Core reference-number service #5 — allocation, yearly reset, never-reused."""

import secrets

from office_connect.core.reference_numbers import allocate_reference_number


async def test_allocation_is_sequential_and_formatted(app_session):
    # Fresh random scope: since R-4-app, real submits COMMIT `RB` allocations,
    # so absolute `RB-…-0001` expectations are no longer rerun-safe (the same
    # determinism trick test_numbers_never_reused always used).
    scope = "T" + secrets.token_hex(3)
    a = await allocate_reference_number(app_session, scope=scope, year=2026)
    b = await allocate_reference_number(app_session, scope=scope, year=2026)
    c = await allocate_reference_number(app_session, scope=scope, year=2026)
    assert a == f"{scope}-2026-0001"
    assert b == f"{scope}-2026-0002"
    assert c == f"{scope}-2026-0003"


async def test_scopes_are_independent(app_session):
    rb_like = "R" + secrets.token_hex(3)
    lq_like = "L" + secrets.token_hex(3)
    rb = await allocate_reference_number(app_session, scope=rb_like, year=2026)
    lq = await allocate_reference_number(app_session, scope=lq_like, year=2026)
    assert rb == f"{rb_like}-2026-0001"
    assert lq == f"{lq_like}-2026-0001"  # its own series


async def test_yearly_reset(app_session):
    scope = "T" + secrets.token_hex(3)
    await allocate_reference_number(app_session, scope=scope, year=2030)
    await allocate_reference_number(app_session, scope=scope, year=2030)
    first_next_year = await allocate_reference_number(app_session, scope=scope, year=2031)
    assert first_next_year == f"{scope}-2031-0001"  # resets per year


async def test_numbers_never_reused(app_session):
    """The counter only advances — a number is never handed out twice, even across
    commits (a soft-deleted/voided record keeps its retired number). A fresh random
    scope keeps this deterministic despite the suite leaving committed rows behind."""
    scope = "T" + secrets.token_hex(3)
    n1 = await allocate_reference_number(app_session, scope=scope, year=2026)
    await app_session.commit()
    n2 = await allocate_reference_number(app_session, scope=scope, year=2026)
    await app_session.commit()
    assert n1.endswith("-0001")
    assert n2.endswith("-0002")
    assert n1 != n2
