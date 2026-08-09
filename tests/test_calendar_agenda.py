"""Stage D-2 — ``GET /api/v1/calendar`` over real HTTP.

**The clock convention, because a calendar is the purest form of the problem.**
This repository has no ``freezegun``/``time-machine``, by design: services take
an injected ``now``/``today`` and HTTP tests move the DATA rather than the clock.
The queue needed ``_backdated`` (a context manager that owns its undo) because
``holder_since`` is compared against ``utc_now()`` inside the service with no way
to ask a different question.

**The calendar's ``?start=&end=`` IS the seam ``_backdated`` was faking.** So the
convention here is simpler and safer: every test creates its rows inside a
PRIVATE YEAR, far outside every fixture's range, and then asks for that year's
window. Absolute assertions are safe, no shared state is mutated, and there is
nothing to undo — which is what the accumulated-row leak found at Stage D-2
(48 stray rows in a seeded reference table) is a warning about.

``urgency`` is the one thing a window cannot isolate — it is relative to TODAY,
not to the requested window — so it is asserted as a SHAPE here and pinned to
exact values by ``deadline.py``'s own unit tests.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from office_connect.core.models import Activity, Holiday
from office_connect.modules.reimbursement.services.lifecycle import submit_claim
from tests.conftest import DEFAULT_TEST_PASSWORD, login
from tests.reimb_lifecycle_helpers import standard_cast
from tests.workflow_helpers import grant_scoped_role

URL = "/api/v1/calendar"

#: A year no fixture and no other test reaches into. Everything this module
#: creates lives here, so "what is in the window" is decided entirely by rows
#: this module wrote — which is what makes absolute assertions honest.
YEAR = 2029
W_START = date(YEAR, 4, 1)
W_END = date(YEAR, 4, 30)


def window(start: date = W_START, end: date = W_END) -> str:
    return f"{URL}?start={start.isoformat()}&end={end.isoformat()}"


async def _activity(session, *, title: str, start: date, end: date | None = None,
                    status: str = "planned", **kw) -> Activity:
    row = Activity(title=title, date_start=start, date_end=end, status=status, **kw)
    session.add(row)
    await session.flush()
    return row


async def _signin(client, user):
    return await login(client, user, DEFAULT_TEST_PASSWORD)


async def _move_trip(session, claim, *, start: date, days: int = 2) -> None:
    """Relocate a whole trip into the private year — dates AND itinerary legs.

    Moving only ``date_depart`` leaves the legs behind, and the per-diem engine
    refuses the result (``no_computable_days``) because the trip window no
    longer contains any leg. That refusal is correct — a trip whose legs are
    three years from its dates is not a trip — so the helper moves both.
    """
    from office_connect.modules.reimbursement.models import ReimbItineraryLeg

    claim.date_depart = start
    claim.date_return = start + timedelta(days=days)
    legs = (
        (
            await session.execute(
                select(ReimbItineraryLeg)
                .where(ReimbItineraryLeg.claim_id == claim.id)
                .order_by(ReimbItineraryLeg.seq)
            )
        )
        .scalars()
        .all()
    )
    for offset, leg in enumerate(legs):
        leg.leg_date = start + timedelta(days=days if offset else 0)
    await session.flush()


def _titles(body) -> list[str]:
    return [e["title"] for day in body["days"] for e in day["events"]]


def _source(body, key):
    return next((s for s in body["sources"] if s["key"] == key), None)


# --------------------------------------------------------------- the gate
async def test_a_user_holding_nothing_is_refused(
    client, make_user, session_redis, seed_rbac, app_session
):
    """403, not ``200 {"days": []}``.

    §9f's rule binds the SURFACE: an empty agenda would claim "nothing is
    happening", which is a statement about the organisation. "This is not yours"
    is a statement about the caller, and it is the true one.
    """
    user, _ = await make_user()  # no roles at all — the no-grants shape
    await app_session.commit()
    await _signin(client, user)

    resp = await client.get(URL)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden"


async def test_an_ordinary_staff_login_can_open_the_calendar(
    client, make_user, session_redis, seed_rbac, app_session
):
    """Decision 7 over real HTTP. A calendar of ORGANISATIONAL activities that
    ordinary staff cannot open is not a calendar of activities.

    ``staff`` is the role driven here because the privileged roles (approver,
    admin_officer, system_admin) require MFA enrolment before their session
    leaves the pending state — a property of those roles, not of this surface.
    The grant itself is asserted for all five below, where MFA is not in the way.
    """
    user, _ = await make_user(roles=("staff",))
    await app_session.commit()
    await _signin(client, user)

    assert (await client.get(URL)).status_code == 200


def test_every_seeded_role_carries_the_calendar_grant():
    """Decision 7, asserted against the grant map itself.

    Written as a positive list rather than a loop over ``ROLE_GRANTS`` so that a
    NEW role does not silently satisfy it: a role added tomorrow must be a
    deliberate decision about whether its holders see the calendar.
    """
    from office_connect.core.seeds.rbac import ROLE_GRANTS

    from office_connect.core.api.calendar import PERMISSION

    for role in ("system_admin", "auditor", "approver", "admin_officer", "staff"):
        assert PERMISSION in ROLE_GRANTS[role], role
    assert set(ROLE_GRANTS) == {
        "system_admin",
        "auditor",
        "approver",
        "admin_officer",
        "staff",
    }, "a new role must decide, deliberately, whether it sees the calendar"


# ------------------------------------------------------------- the window
async def test_the_window_defaults_to_today_forward_from_the_servers_clock(
    client, make_user, session_redis, seed_rbac, app_session
):
    """Defaults come from the SERVER's Manila day. Two people asking "what is
    coming up" from different timezones must be given the same window."""
    user, _ = await make_user(roles=("staff",))
    await app_session.commit()
    await _signin(client, user)

    body = (await client.get(URL)).json()
    assert body["start"] == body["today"]
    assert date.fromisoformat(body["end"]) == date.fromisoformat(body["start"]) + timedelta(days=30)
    assert body["window_clamped"] is False


async def test_an_over_long_window_is_clamped_and_says_so(
    client, make_user, session_redis, seed_rbac, app_session
):
    """A bound the client cannot see is a bound the client will eventually
    contradict (§9g). Clamping silently would let a page promise a year."""
    user, _ = await make_user(roles=("staff",))
    await app_session.commit()
    await _signin(client, user)

    body = (await client.get(window(W_START, date(YEAR + 2, 1, 1)))).json()
    assert body["window_clamped"] is True
    assert body["start"] == W_START.isoformat()
    assert date.fromisoformat(body["end"]) == W_START + timedelta(
        days=body["window_max_days"]
    )


async def test_a_backwards_window_is_a_422_never_a_silent_swap(
    client, make_user, session_redis, seed_rbac, app_session
):
    """Swapping the dates would answer a question nobody asked."""
    user, _ = await make_user(roles=("staff",))
    await app_session.commit()
    await _signin(client, user)

    resp = await client.get(window(W_END, W_START))
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


# ---------------------------------------------------------- the activities
async def test_activities_are_tenant_wide_and_a_stranger_sees_them(
    client, make_user, session_redis, seed_rbac, app_session
):
    """Decision 12, asserted rather than assumed. The spine only works as a join
    key if everyone can see it — and this is the assertion that will fail the day
    somebody adds a scope filter without changing the decision."""
    await _activity(
        app_session, title=f"[{YEAR}] Tenant-wide activity", start=date(YEAR, 4, 10)
    )
    await app_session.commit()

    user, _ = await make_user(roles=("staff",))  # no oversight, no own claims
    await app_session.commit()
    await _signin(client, user)

    body = (await client.get(window())).json()
    assert f"[{YEAR}] Tenant-wide activity" in _titles(body)
    assert _source(body, "core.activity")["bounded_note"] is None


async def test_an_activity_spanning_the_window_edge_is_included(
    client, make_user, session_redis, seed_rbac, app_session
):
    """Overlap, not containment. A week-long activity that starts before the
    window is still happening during it — dropping it is the calendar quietly
    lying about a week somebody is away."""
    await _activity(
        app_session,
        title=f"[{YEAR}] Straddles the start",
        start=W_START - timedelta(days=3),
        end=W_START + timedelta(days=2),
    )
    await app_session.commit()

    user, _ = await make_user(roles=("staff",))
    await app_session.commit()
    await _signin(client, user)

    body = (await client.get(window())).json()
    assert f"[{YEAR}] Straddles the start" in _titles(body)


async def test_a_soft_deleted_activity_never_appears(
    client, make_user, session_redis, seed_rbac, app_session
):
    from office_connect.core.soft_delete import soft_delete

    row = await _activity(
        app_session, title=f"[{YEAR}] Deleted", start=date(YEAR, 4, 12)
    )
    soft_delete(row)
    await app_session.commit()

    user, _ = await make_user(roles=("staff",))
    await app_session.commit()
    await _signin(client, user)

    assert f"[{YEAR}] Deleted" not in _titles((await client.get(window())).json())


async def test_the_free_form_custom_blob_never_crosses_the_wire(
    client, make_user, session_redis, seed_rbac, app_session
):
    """``core_activities.custom`` is free JSONB on a TENANT-WIDE surface — a
    tenant can put anything in it, including the thing decision 12 is about.
    Excluded by construction; this is the test that keeps it excluded."""
    await _activity(
        app_session,
        title=f"[{YEAR}] Has custom",
        start=date(YEAR, 4, 14),
        custom={"secret_note": "must-never-be-served"},
    )
    await app_session.commit()

    user, _ = await make_user(roles=("staff",))
    await app_session.commit()
    await _signin(client, user)

    raw = (await client.get(window())).text
    assert "must-never-be-served" not in raw
    assert "secret_note" not in raw


async def test_days_with_nothing_on_them_are_omitted(
    client, make_user, session_redis, seed_rbac, app_session
):
    """An agenda is a list of days that HAVE something. 92 empty rows is a month
    grid wearing a list's markup, and it hands a screen reader 92 headings with
    nothing underneath."""
    await _activity(
        app_session, title=f"[{YEAR}] Only day", start=date(YEAR, 4, 15)
    )
    await app_session.commit()

    user, _ = await make_user(roles=("staff",))
    await app_session.commit()
    await _signin(client, user)

    body = (await client.get(window())).json()
    assert all(day["events"] for day in body["days"])
    assert [d["date"] for d in body["days"]] == sorted(d["date"] for d in body["days"])


@asynccontextmanager
async def _holiday(session, *, day: date, name: str):
    """Create a holiday for the body of a test, then take it back.

    **A context manager rather than a bare insert, and that is not fussiness.**
    ``core_holidays`` carries a live-rows-only unique index on
    ``(calendar_date, name, scope)``, so a leaked row makes the SECOND run of
    this test fail on a constraint violation — which is precisely the class of
    accumulated-state defect that made three suite runs at #29 fail three
    different ways. ``_backdated`` learned this at R-9: a docstring asking the
    caller to clean up is not an enforcement mechanism.

    Undone by soft delete (the app role physically cannot hard-delete), which is
    enough: the unique index is partial on ``deleted_at IS NULL``.
    """
    from office_connect.core.soft_delete import soft_delete

    row = Holiday(
        calendar_date=day, name=name, holiday_type="regular", scope="national"
    )
    session.add(row)
    await session.commit()
    try:
        yield row
    finally:
        soft_delete(row)
        await session.commit()


async def test_a_holiday_is_named_not_merely_greyed(
    client, make_user, session_redis, seed_rbac, app_session
):
    """The working-day engine already knows the day does not count; a calendar
    can say WHY. One holiday load for the whole window (rule 10's engine, used
    the way it was built)."""
    holiday_day = date(YEAR, 4, 9)
    async with _holiday(app_session, day=holiday_day, name="Araw ng Kagitingan (test)"):
        await _activity(
            app_session, title=f"[{YEAR}] On a holiday", start=holiday_day
        )
        await app_session.commit()

        user, _ = await make_user(roles=("staff",))
        await app_session.commit()
        await _signin(client, user)

        body = (await client.get(window())).json()
        day = next(d for d in body["days"] if d["date"] == holiday_day.isoformat())
        assert day["is_nonworking"] is True
        assert day["nonworking_label"] == "Araw ng Kagitingan (test)"


# ------------------------------------------------------------- the sources
async def test_a_flag_off_module_is_absent_from_sources_not_merely_empty(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_off
):
    """api-standards §9/§9k: a module with its flag off must be
    indistinguishable from one that was never built. An empty ``reimb.travel``
    block would announce a module the tenant has not bought."""
    user, _ = await make_user(roles=("staff",))
    await app_session.commit()
    await _signin(client, user)

    body = (await client.get(window())).json()
    keys = [s["key"] for s in body["sources"]]
    assert keys == ["core.activity"], keys


async def test_a_flag_on_module_contributes_its_sources(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    user, _ = await make_user(roles=("staff",))
    await app_session.commit()
    await _signin(client, user)

    body = (await client.get(window())).json()
    keys = sorted(s["key"] for s in body["sources"])
    assert keys == ["core.activity", "reimb.liquidation", "reimb.travel"]


async def test_total_is_the_sum_of_the_sources_pre_cap_counts(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """§9f: ``total`` is the count BEFORE any cap, and the page renders the
    server's number rather than counting the rows it can see."""
    for offset in range(3):
        await _activity(
            app_session,
            title=f"[{YEAR}] Counted {offset}",
            start=date(YEAR, 4, 20) + timedelta(days=offset),
        )
    await app_session.commit()

    user, _ = await make_user(roles=("staff",))
    await app_session.commit()
    await _signin(client, user)

    body = (await client.get(window())).json()
    assert body["total"] == sum(s["total"] for s in body["sources"])
    assert body["total"] >= 3


# -------------------------------------------------------------- the travel
async def test_an_overseer_sees_the_trips_they_oversee(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    scene = await standard_cast(app_session, make_user)
    await _move_trip(app_session, scene.claim, start=date(YEAR, 4, 5))
    await submit_claim(app_session, claim_id=scene.claim.id, actor_user_id=scene.owner.id)
    await grant_scoped_role(
        app_session, user=scene.admin, role_code="staff", org_unit_id=None
    )
    await app_session.commit()

    await _signin(client, scene.admin)
    body = (await client.get(window())).json()

    refs = [e["ref"] for day in body["days"] for e in day["events"]]
    assert f"claim:{scene.claim.id}" in refs


async def test_a_traveller_sees_their_own_trip_including_a_draft(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """The own-claims branch has no ``WorkflowInstance`` join on purpose: an
    unsubmitted trip is still a trip you are taking, and My Work already treats
    a draft as the traveller's live work."""
    scene = await standard_cast(app_session, make_user)
    await _move_trip(app_session, scene.claim, start=date(YEAR, 4, 11), days=1)
    await app_session.commit()
    assert scene.claim.workflow_instance_id is None, "this test is about a DRAFT"

    await _signin(client, scene.owner)
    body = (await client.get(window())).json()

    refs = [e["ref"] for day in body["days"] for e in day["events"]]
    assert f"claim:{scene.claim.id}" in refs
    note = _source(body, "reimb.travel")["bounded_note"]
    assert note == (
        "Travel shown here is your own. Colleagues' claims are not on this calendar."
    )


async def test_a_claim_with_no_dates_is_not_on_any_calendar(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    scene = await standard_cast(app_session, make_user)
    scene.claim.date_depart = None
    scene.claim.date_return = None
    await app_session.commit()

    await _signin(client, scene.owner)
    body = (await client.get(window())).json()
    refs = [e["ref"] for day in body["days"] for e in day["events"]]
    assert f"claim:{scene.claim.id}" not in refs


async def test_the_bounded_note_never_carries_a_count_of_hidden_rows(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """Decision 9 / §9h. "3 more you cannot see" tells a division chief how much
    travel a sibling division booked — a disclosure they could not have assembled
    by opening records one at a time. State the rule; never the residue."""
    scene = await standard_cast(app_session, make_user)
    await _move_trip(app_session, scene.claim, start=date(YEAR, 4, 18))
    await submit_claim(app_session, claim_id=scene.claim.id, actor_user_id=scene.owner.id)
    await app_session.commit()

    stranger, _ = await make_user(roles=("staff",))
    await app_session.commit()
    await _signin(client, stranger)

    note = _source((await client.get(window())).json(), "reimb.travel")["bounded_note"]
    assert note is not None
    assert not any(ch.isdigit() for ch in note), note


# ---------------------------------------------------------- the liquidation
async def test_a_liquidation_clock_appears_once_for_its_own_claimant(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """ONE row per obligation. ``reimb_claims.liquidation_deadline`` is a mirror
    of ``reimb_cash_advances.deadline_date`` (``cash_advance.link_claim``: "a
    MIRROR, written here only"), so feeding both would draw two countdown rows
    for one advance on the same day."""
    from office_connect.modules.reimbursement.services import cash_advance as ca

    scene = await standard_cast(app_session, make_user)
    advance = await ca.create_cash_advance(
        app_session,
        claimant_id=scene.staff.id,
        dv_no=f"DV-{YEAR}-CAL-1",
        dv_date=date(YEAR, 3, 1),
        amount="9000.00",
        date_return=date(YEAR, 3, 20),
        actor_user_id=scene.admin.id,
    )
    await app_session.commit()
    assert advance.deadline_date is not None

    await _signin(client, scene.owner)
    body = (
        await client.get(window(advance.deadline_date, advance.deadline_date))
    ).json()

    liq = [
        e
        for day in body["days"]
        for e in day["events"]
        if e["source"] == "reimb.liquidation"
    ]
    assert len(liq) == 1, liq
    assert liq[0]["ref"] == f"advance:{advance.id}"
    assert liq[0]["urgency"] in (None, "due_soon", "overdue")
    # A calendar has no business carrying financial identifiers.
    assert "9000" not in body_text(body)
    assert f"DV-{YEAR}-CAL-1" not in body_text(body)


def body_text(body) -> str:
    import json

    return json.dumps(body)


async def test_a_colleagues_liquidation_clock_is_not_on_your_calendar(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """Decision 11 — own advances only. Widening this needs a set-form scope rule
    that does not exist anywhere in the module (calendar.md §6b)."""
    from office_connect.modules.reimbursement.services import cash_advance as ca

    scene = await standard_cast(app_session, make_user)
    advance = await ca.create_cash_advance(
        app_session,
        claimant_id=scene.staff.id,
        dv_no=f"DV-{YEAR}-CAL-2",
        dv_date=date(YEAR, 3, 1),
        amount="7000.00",
        date_return=date(YEAR, 3, 25),
        actor_user_id=scene.admin.id,
    )
    await app_session.commit()

    # The ADMIN OFFICER — who may manage this advance on its own screen — still
    # does not get another person's clock on their calendar.
    await _signin(client, scene.admin)
    body = (
        await client.get(window(advance.deadline_date, advance.deadline_date))
    ).json()

    refs = [e["ref"] for day in body["days"] for e in day["events"]]
    assert f"advance:{advance.id}" not in refs
    assert _source(body, "reimb.liquidation")["bounded_note"] == (
        "Liquidation deadlines shown here are your own."
    )
