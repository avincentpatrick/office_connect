"""R-6-clock QA gate: the COA 30-day liquidation deadline.

Spec §6.2 + §4 + R-0 item 1 (closed 2026-08-04): 30 days from
``cash_advance.date_return``, CALENDAR by default per COA Circular 97-002, with
``basis`` honoured as config so confirming DOH working-day practice later is a
config edit rather than a code change.

The pure calculator is tested with no session at all — that is the point of
keeping ``services/deadline.py`` I/O-free (the same shape as ``per_diem.py``).
"""

from datetime import date

import pytest

from office_connect.modules.reimbursement.services import deadline as dl


def _nonworking(*days: date) -> frozenset[date]:
    return frozenset(days)


# --- read_rule: total, never raises -----------------------------------------


def test_read_rule_takes_the_seeded_calendar_default():
    rule = dl.read_rule({dl.DEADLINE_KEY: {"days": 30, "basis": "calendar"}})
    assert (rule.days, rule.basis, rule.reason) == (30, "calendar", "configured")


def test_read_rule_honours_a_working_day_override():
    """The whole point of closing R-0 with a switch: a tenant flips this row and
    every deadline in the module follows, with no deployment."""
    rule = dl.read_rule({dl.DEADLINE_KEY: {"days": 30, "basis": "working"}})
    assert (rule.days, rule.basis) == (30, "working")


@pytest.mark.parametrize(
    "value,expected_reason",
    [
        (None, "no_config_row"),
        ({}, "unreadable_days"),
        ({"days": "thirty"}, "unreadable_days"),
        ({"days": 0}, "non_positive_days"),
        ({"days": -5}, "non_positive_days"),
    ],
)
def test_unreadable_config_falls_back_to_the_coa_default(value, expected_reason):
    """Fails SHORT, and says why. Compliance clocks fail closed — the opposite
    of the checklist grammar's fail-open, and deliberately so: an unparseable
    rule produces a visible flag, whereas a deadline that failed open would
    quietly hand a traveller time they do not legally have."""
    rule = dl.read_rule({dl.DEADLINE_KEY: value} if value is not None else {})
    assert rule.days == dl.DEFAULT_DAYS
    assert rule.basis == dl.CALENDAR
    assert rule.reason == expected_reason


def test_an_unknown_basis_keeps_the_configured_day_count():
    """Only the basis was unreadable. Discarding a legitimate 45 because someone
    typoed 'calender' would be a second wrong answer on top of the first."""
    rule = dl.read_rule({dl.DEADLINE_KEY: {"days": 45, "basis": "calender"}})
    assert (rule.days, rule.basis, rule.reason) == (45, "calendar", "unknown_basis")


# --- liquidation_deadline ---------------------------------------------------


def test_calendar_basis_is_plain_arithmetic():
    """COA 97-002's own reading: 30 days after return to official station."""
    rule = dl.DeadlineRule(30, dl.CALENDAR)
    assert dl.liquidation_deadline(
        date_return=date(2026, 7, 3), rule=rule
    ) == date(2026, 8, 2)


def test_calendar_basis_ignores_weekends_and_holidays():
    """A calendar deadline landing on a Sunday stays on that Sunday — COA's text
    contains no roll-forward rule, and inventing one would silently extend every
    deadline in the tenant."""
    rule = dl.DeadlineRule(30, dl.CALENDAR)
    due = dl.liquidation_deadline(
        date_return=date(2026, 7, 3),
        rule=rule,
        nonworking=_nonworking(date(2026, 8, 2)),
    )
    assert due == date(2026, 8, 2)


def test_calendar_basis_crosses_a_year_boundary():
    rule = dl.DeadlineRule(30, dl.CALENDAR)
    assert dl.liquidation_deadline(
        date_return=date(2026, 12, 20), rule=rule
    ) == date(2027, 1, 19)


def test_working_basis_skips_weekends():
    """Fri 2026-07-03 + 10 working days = Fri 2026-07-17 (two weekends out)."""
    rule = dl.DeadlineRule(10, dl.WORKING)
    assert dl.liquidation_deadline(
        date_return=date(2026, 7, 3), rule=rule, nonworking=frozenset()
    ) == date(2026, 7, 17)


def test_working_basis_skips_the_holiday_calendar():
    """One injected holiday pushes the deadline out by exactly one working day —
    the shared ``core/workdays.py`` engine, not a second implementation."""
    rule = dl.DeadlineRule(10, dl.WORKING)
    due = dl.liquidation_deadline(
        date_return=date(2026, 7, 3),
        rule=rule,
        nonworking=_nonworking(date(2026, 7, 13)),
    )
    assert due == date(2026, 7, 20)


def test_working_basis_is_materially_longer_than_calendar():
    """Why R-0 mattered: the same '30 days' is six weeks apart between bases.
    This is the number that would have been silently wrong had we guessed."""
    calendar = dl.liquidation_deadline(
        date_return=date(2026, 7, 3), rule=dl.DeadlineRule(30, dl.CALENDAR)
    )
    working = dl.liquidation_deadline(
        date_return=date(2026, 7, 3),
        rule=dl.DeadlineRule(30, dl.WORKING),
        nonworking=frozenset(),
    )
    assert calendar == date(2026, 8, 2)
    assert working == date(2026, 8, 14)
    assert (working - calendar).days == 12


def test_no_return_date_means_no_clock():
    """A trip that has not happened has no deadline. A zero or an epoch date
    would put a countdown on a surface that should say 'not started'."""
    assert (
        dl.liquidation_deadline(
            date_return=None, rule=dl.DeadlineRule(30, dl.CALENDAR)
        )
        is None
    )


# --- the countdown a human reads -------------------------------------------


@pytest.mark.parametrize(
    "today,expected",
    [
        (date(2026, 8, 2), 0),
        (date(2026, 8, 1), 1),
        (date(2026, 7, 26), 7),
        (date(2026, 8, 5), -3),
    ],
)
def test_days_remaining_is_always_calendar_days(today, expected):
    """Whatever basis produced the deadline. '3 working days left' rendered
    beside a date three weekends away is a countdown nobody can read."""
    assert (
        dl.days_remaining(deadline=date(2026, 8, 2), today=today) == expected
    )


@pytest.mark.parametrize(
    "today,expected",
    [
        (date(2026, 7, 1), dl.ON_TRACK),
        (date(2026, 7, 25), dl.ON_TRACK),  # 8 days out — one day outside D-7
        (date(2026, 7, 26), dl.DUE_SOON),  # exactly 7 → spec §6.3's window
        (date(2026, 8, 2), dl.DUE_SOON),  # due today is still not yet late
        (date(2026, 8, 3), dl.OVERDUE),
    ],
)
def test_deadline_state_uses_the_spec_6_3_seven_day_window(today, expected):
    """§6.3's 'Due Soon (≤ 7 days)' belongs to THIS clock. R-4-screens
    deliberately did not apply it to the 3-working-day approval SLA, where
    every item would have been born amber."""
    assert dl.deadline_state(deadline=date(2026, 8, 2), today=today) == expected


def test_no_deadline_has_no_state():
    assert dl.deadline_state(deadline=None, today=date(2026, 8, 2)) is None
    assert dl.days_remaining(deadline=None, today=date(2026, 8, 2)) is None
