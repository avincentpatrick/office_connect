"""R-6-clock QA gate: the D-7 / D-3 / D-0 / overdue ladder (spec §12).

Spec §12's row reads *"Liquidation D-7 / D-3 / D-0 / overdue → Claimant (CA
holder) · COA warning copy at D-0"*, and §12's closing line adds *"email only
for liquidation D-3/D-0 (transactional)"*. Every rung here is that sentence
under test, plus the two things the sweep is also responsible for: flipping the
advance to ``overdue`` (spec §5.4's status, which §13's "overdue CAs count + ₱"
report has to be able to sum) and never nudging anyone but the holder.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from office_connect.core.models.notification import NotificationOutbox
from office_connect.modules.reimbursement.seeds import apply_reimbursement_seeds
from office_connect.modules.reimbursement.services import cash_advance as ca
from office_connect.modules.reimbursement.services.notify import (
    LIQUIDATION_DEDUP_PREFIX,
    sweep_liquidation_reminders,
)
from tests.reimbursement_helpers import make_staff
from tests.workflow_helpers import grant_scoped_role, make_org_unit

UTC = timezone.utc
RETURN = date(2026, 7, 3)
DUE = date(2026, 8, 2)  # 30 calendar days after RETURN


def _at(day: date) -> datetime:
    """10:00 Manila on ``day`` — the beat's real firing shape is 08:35, but any
    time inside the Manila day resolves to the same date."""
    return datetime(day.year, day.month, day.day, 2, 0, tzinfo=UTC)


@pytest.fixture
async def traveller(app_session, make_user):
    await apply_reimbursement_seeds(app_session)
    office = await make_org_unit(app_session, kind="office")
    division = await make_org_unit(app_session, kind="division", parent=office)
    staff = await make_staff(app_session, division_id=division.id)
    owner, _ = await make_user(roles=("staff",), staff_id=staff.id)
    admin, _ = await make_user()
    await grant_scoped_role(
        app_session, user=admin, role_code="admin_officer", org_unit_id=office.id
    )
    advance = await ca.create_cash_advance(
        app_session,
        claimant_id=staff.id,
        amount=Decimal("5000.00"),
        actor_user_id=admin.id,
        dv_no="DV-LADDER-1",
        date_return=RETURN,
        now=_at(date(2026, 7, 4)),
    )
    await app_session.flush()
    assert advance.deadline_date == DUE
    return SimpleNamespace(staff=staff, owner=owner, admin=admin, advance=advance)


async def _rows(session, advance_id: int, token: str, channel: str):
    key = f"{LIQUIDATION_DEDUP_PREFIX}:{advance_id}:{token}:{channel}"
    return (
        (
            await session.execute(
                select(NotificationOutbox).where(
                    NotificationOutbox.dedup_key == key
                )
            )
        )
        .scalars()
        .all()
    )


# --- The rungs ---------------------------------------------------------------


async def test_nothing_fires_while_the_deadline_is_far_off(app_session, traveller):
    """Eight days out is one day outside the D-7 window. A ladder that started
    nagging at CA creation would be noise, not a warning."""
    result = await sweep_liquidation_reminders(
        app_session, now=_at(date(2026, 7, 25))
    )
    assert result["nudged"] == 0
    assert await _rows(app_session, traveller.advance.id, "d7", "in_app") == []


async def test_d7_fires_in_app_only(app_session, traveller):
    """Spec §12: email is reserved for D-3 and D-0. A week's notice does not
    warrant a transactional email that bypasses opt-outs."""
    await sweep_liquidation_reminders(app_session, now=_at(date(2026, 7, 26)))

    (row,) = await _rows(app_session, traveller.advance.id, "d7", "in_app")
    assert row.channel == "in_app"
    assert row.recipient_user_id == traveller.owner.id  # the HOLDER, nobody else
    assert row.module == "reimbursement"
    assert "DV-LADDER-1" in row.subject
    assert await _rows(app_session, traveller.advance.id, "d7", "email") == []


async def test_d3_fires_in_app_and_email(app_session, traveller):
    await sweep_liquidation_reminders(app_session, now=_at(date(2026, 7, 30)))

    (in_app,) = await _rows(app_session, traveller.advance.id, "d3", "in_app")
    (email,) = await _rows(app_session, traveller.advance.id, "d3", "email")
    assert in_app.channel == "in_app"
    assert email.channel == "email"
    assert email.recipient_email == traveller.owner.email
    # Transactional: a traveller may mute workflow chatter, never a COA clock.
    assert email.meta["notification_class"] == "transactional"


async def test_d0_carries_the_coa_warning_copy_from_config(app_session, traveller):
    """Spec §12: "COA warning copy at D-0". The sentence comes from
    ``liquidation.overdue_note`` with its legal source — the resident COA
    auditor owns that wording, not this module."""
    await sweep_liquidation_reminders(app_session, now=_at(DUE))

    (in_app,) = await _rows(app_session, traveller.advance.id, "d0", "in_app")
    (email,) = await _rows(app_session, traveller.advance.id, "d0", "email")
    assert "6% interest" in in_app.body_text
    assert "deducted from your salary" in in_app.body_text
    assert "6% interest" in email.body_text


async def test_d7_copy_does_not_carry_the_warning(app_session, traveller):
    """The consequence copy appears where it applies. On a page that always
    says "your salary may be deducted", nobody reads it by D-0."""
    await sweep_liquidation_reminders(app_session, now=_at(date(2026, 7, 26)))
    (row,) = await _rows(app_session, traveller.advance.id, "d7", "in_app")
    assert "6% interest" not in row.body_text


# --- Overdue -----------------------------------------------------------------


async def test_past_the_deadline_flips_the_status_and_nudges(app_session, traveller):
    # Assertions target OUR advance, never the sweep's global counters: the
    # shared dev DB carries advances from other tests, so a count would be
    # fragile for reasons that have nothing to do with this behaviour (the
    # same caveat test_reimb_sla_notifications.py records at the top).
    await sweep_liquidation_reminders(app_session, now=_at(date(2026, 8, 3)))
    assert traveller.advance.status == "overdue"

    (row,) = await _rows(app_session, traveller.advance.id, "overdue:0", "in_app")
    assert "overdue" in row.body_text.lower()
    # Overdue repeats stay in-app — spec §12 names D-3/D-0 for email, and a
    # daily email about a missed deadline trains people to filter the sender.
    assert await _rows(app_session, traveller.advance.id, "overdue:0", "email") == []


async def test_the_overdue_rung_repeats_on_the_working_day_cadence(
    app_session, traveller
):
    """``sla.reminder_repeat_days`` = 2 WORKING days. The deadline itself is
    calendar; how often we chase it is a different question, and nobody should
    be nagged on a Sunday."""
    await sweep_liquidation_reminders(app_session, now=_at(date(2026, 8, 3)))
    assert await _rows(app_session, traveller.advance.id, "overdue:0", "in_app")

    # Mon 08-03 → Fri 08-07 is 4 working days → k = 4 // 2 = 2.
    await sweep_liquidation_reminders(app_session, now=_at(date(2026, 8, 7)))
    assert await _rows(app_session, traveller.advance.id, "overdue:2", "in_app")


async def test_a_settled_advance_drops_out_of_the_work_list(app_session, traveller):
    traveller.advance.status = "settled"
    await app_session.flush()
    await sweep_liquidation_reminders(app_session, now=_at(date(2026, 8, 3)))
    assert await _rows(app_session, traveller.advance.id, "overdue:0", "in_app") == []
    assert traveller.advance.status == "settled"  # never re-flipped to overdue


# --- Robustness --------------------------------------------------------------


async def test_the_sweep_is_idempotent(app_session, traveller):
    """Outbox dedup keys, exactly like the SLA ladder: a beat that fires twice
    (retry, restart, manual run) sends nothing extra."""
    for _ in range(3):
        await sweep_liquidation_reminders(app_session, now=_at(date(2026, 7, 30)))
    assert len(await _rows(app_session, traveller.advance.id, "d3", "in_app")) == 1
    assert len(await _rows(app_session, traveller.advance.id, "d3", "email")) == 1


async def test_a_missed_beat_warns_at_the_level_that_is_now_true(
    app_session, traveller
):
    """Milestones are "the most urgent threshold REACHED", not "days_remaining
    == exactly n". A worker outage over D-7 must not mean silence — and it must
    not mean sending "7 days left" on the day 3 remain."""
    await sweep_liquidation_reminders(app_session, now=_at(date(2026, 7, 30)))

    assert await _rows(app_session, traveller.advance.id, "d3", "in_app")
    assert await _rows(app_session, traveller.advance.id, "d7", "in_app") == []


async def test_only_the_holder_is_ever_nudged(app_session, traveller):
    """Spec §7.4's non-negotiable, carried onto this clock: no superior, no
    Accounting cc. Visibility does the escalating, on the dashboards."""
    await sweep_liquidation_reminders(app_session, now=_at(DUE))
    rows = (
        (
            await app_session.execute(
                select(NotificationOutbox).where(
                    NotificationOutbox.dedup_key.like(
                        f"{LIQUIDATION_DEDUP_PREFIX}:{traveller.advance.id}:%"
                    )
                )
            )
        )
        .scalars()
        .all()
    )
    assert rows
    assert {r.recipient_user_id for r in rows} == {traveller.owner.id}


async def test_an_advance_with_no_login_still_flips_overdue(
    app_session, make_user, traveller
):
    """The overdue COUNT is a financial fact about the advance. It must not
    depend on whether the traveller happens to have a platform account —
    spec §13 asks for the number and the peso total either way."""
    loner = await make_staff(app_session)
    admin = traveller.admin
    advance = await ca.create_cash_advance(
        app_session,
        claimant_id=loner.id,
        amount=Decimal("1000.00"),
        actor_user_id=admin.id,
        date_return=RETURN,
        now=_at(date(2026, 7, 4)),
    )
    await app_session.flush()

    await sweep_liquidation_reminders(app_session, now=_at(date(2026, 8, 3)))
    assert advance.status == "overdue"
    assert await _rows(app_session, advance.id, "overdue:0", "in_app") == []


async def test_an_advance_with_no_deadline_is_never_swept(
    app_session, make_user, traveller
):
    """No return date → no clock → nothing to be late against."""
    other = await make_staff(app_session)
    advance = await ca.create_cash_advance(
        app_session,
        claimant_id=other.id,
        amount=Decimal("1000.00"),
        actor_user_id=traveller.admin.id,
        now=_at(date(2026, 7, 4)),
    )
    await app_session.flush()
    await sweep_liquidation_reminders(app_session, now=_at(date(2027, 1, 1)))
    assert advance.status == "open"


async def test_the_sweep_drains_rather_than_truncating(app_session, traveller):
    """Written drained from the start — the SLA ladder had to have a
    single-``LIMIT`` starvation bug fixed out of it first (sessions 18–20), and
    copying that shape into a second ladder would have repeated it."""
    result = await sweep_liquidation_reminders(
        app_session, now=_at(DUE), page_size=1, max_pages=5_000
    )
    assert result["drained"] is True
    assert await _rows(app_session, traveller.advance.id, "d0", "in_app")
