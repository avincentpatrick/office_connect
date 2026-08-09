"""Increment 4 Group C — working-day engine + holiday/deadline calendar.

Gate line: "holiday-calendar working-day math correct across a holiday/weekend/
suspension."

⚠ Every committed row here lands in a SEEDED reference table, so it goes in
through ``owned_row`` and comes back out again. Tokenized natural keys were the
old defence and they are not one: this module is where the #29 defect was born —
one ``csmr_to_arta_<hash>`` row per run, 48 of them against 22 real seeds by the
time anyone looked. ``seed_addition_guard`` now fails the run if this regresses.
"""

import uuid
from contextlib import AsyncExitStack
from datetime import date

from office_connect.core import workdays
from office_connect.core.models import ComplianceDeadline, Holiday

from tests.conftest import owned_row


def _tok() -> str:
    return uuid.uuid4().hex[:10]


# 2026-07-23 is a Thursday.
THU = date(2026, 7, 23)
FRI = date(2026, 7, 24)
SAT = date(2026, 7, 25)
SUN = date(2026, 7, 26)
MON = date(2026, 7, 27)
TUE = date(2026, 7, 28)


def test_weekend_is_non_working():
    assert workdays.is_working_day(THU, set())
    assert not workdays.is_working_day(SAT, set())
    assert not workdays.is_working_day(SUN, set())


def test_next_working_day_rolls_over_weekend():
    # A deadline landing on Saturday rolls forward to Monday.
    assert workdays.next_working_day(SAT, set()) == MON


def test_add_working_days_skips_weekend():
    # Thu + 1 WD = Fri; Thu + 2 WD skips the weekend to Mon.
    assert workdays.add_working_days(THU, 1, set()) == FRI
    assert workdays.add_working_days(THU, 2, set()) == MON


def test_add_working_days_crossing_a_holiday_adds_a_day():
    # Declare Friday a regular holiday: Thu + 1 WD is now Monday, not Friday.
    nonworking = {FRI}
    assert workdays.add_working_days(THU, 1, nonworking) == MON


def test_work_suspension_mid_window_excluded():
    # Monday is a "walang pasok" suspension → Thu + 2 WD becomes Tuesday.
    nonworking = {MON}
    assert workdays.add_working_days(THU, 2, nonworking) == TUE


def test_special_working_day_still_counts():
    # A special_working day is NOT in the nonworking set, so a weekday one counts.
    # (Friday is a working day when nothing marks it non-working.)
    assert workdays.add_working_days(THU, 1, set()) == FRI


def test_working_days_between_pairs_with_add():
    nonworking = {FRI}
    target = workdays.add_working_days(THU, 3, nonworking)
    assert workdays.working_days_between(THU, target, nonworking) == 3
    assert workdays.working_days_between(THU, THU, nonworking) == 0
    assert workdays.working_days_between(target, THU, nonworking) == -3


def test_adjust_backward():
    assert workdays.adjust_to_working_day(SUN, set(), direction="backward") == FRI


async def test_load_nonworking_dates_from_db(app_session):
    tok = _tok()
    rows = [
        Holiday(
            calendar_date=date(2026, 8, 21),
            name=f"Ninoy Aquino Day {tok}",
            holiday_type="special_non_working",
        ),
        Holiday(
            calendar_date=date(2026, 8, 25),
            name=f"Localized suspension {tok}",
            holiday_type="work_suspension",
        ),
        Holiday(
            calendar_date=date(2026, 8, 26),
            name=f"Founding Anniversary {tok}",
            holiday_type="special_working",
        ),
    ]
    async with AsyncExitStack() as stack:
        for row in rows:
            await stack.enter_async_context(owned_row(app_session, row))

        nonworking = await workdays.load_nonworking_dates(
            app_session, date(2026, 8, 1), date(2026, 8, 31)
        )
        assert date(2026, 8, 21) in nonworking
        assert date(2026, 8, 25) in nonworking
        # special_working is NOT non-working.
        assert date(2026, 8, 26) not in nonworking


async def test_compliance_deadline_persists(app_session):
    dl = ComplianceDeadline(
        code=f"csmr_to_arta_{_tok()}",
        name="CSMR to ARTA",
        authority="ARTA MC 2022-01",
        cadence="annual",
        due_rule={"kind": "fixed_date", "month": 4, "day": 30},
        tenant_id=None,
        effective_from=date(2026, 1, 1),
    )
    async with owned_row(app_session, dl):
        assert dl.id is not None
        assert dl.use_working_day_math is True
