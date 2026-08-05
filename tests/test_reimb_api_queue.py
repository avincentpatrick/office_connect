"""R-7-queue — the oversight queue (``GET /claims``), the module's first LIST.

Two things are on trial here and the first is the important one.

**Scope.** Every earlier read path asked "may this actor read THIS claim". A
list asks "which claims may this actor see", and the naive answer — reuse the
route's ``reimb.claim.read`` — publishes every colleague's trips and peso totals
to every employee, because the ``staff`` role holds that permission GLOBALLY so
a traveller can read their own claim. So the leakage tests come first and they
are the point of the file.

**The FMS follow-up clock (spec §7 rule 5).** ``handed_to_fms`` is deliberately
never SLA-stamped, so ">10 working days with FMS" is a filter and not a
notification. It is counted in Manila WORKING days against the real holiday
calendar, which is why a holiday inside the window has its own test.

Every overseer here is an ``admin_officer``: that is spec §7 rule 5's actor, and
it is also the only oversight role that does not demand MFA at login, so the
tests stay about the queue instead of about TOTP replay.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import timedelta

from office_connect.core.models import Holiday
from office_connect.core.time import to_manila, utc_now
from office_connect.core.workdays import load_nonworking_dates
from office_connect.modules.reimbursement.services import status as st
from office_connect.modules.reimbursement.services.external import record_payout
from office_connect.modules.reimbursement.services.lifecycle import (
    claim_action,
    submit_claim,
)
from tests.conftest import DEFAULT_TEST_PASSWORD, login
from tests.reimb_lifecycle_helpers import standard_cast, trip_claim
from tests.reimbursement_helpers import make_staff
from tests.workflow_helpers import grant_scoped_role, make_org_unit

BASE = "/api/v1/reimbursement"


async def _at_fms(app_session, make_user, **cast_kw):
    """The standard cast, driven to ``handed_to_fms`` — the state whose whole
    problem is that it appears in nobody's My Work."""
    cast = await standard_cast(app_session, make_user, **cast_kw)
    await submit_claim(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.owner.id
    )
    await claim_action(
        app_session, claim_id=cast.claim.id, action="approve",
        actor_user_id=cast.approver.id,
    )
    await claim_action(
        app_session, claim_id=cast.claim.id, action="approve",
        actor_user_id=cast.admin.id,
    )
    assert cast.claim.status == st.HANDED_TO_FMS
    return cast


async def _global_admin(app_session, make_user):
    """An Admin Officer with an unscoped grant — for the tests about the clock
    rather than about scope."""
    boss, _ = await make_user()
    await grant_scoped_role(
        app_session, user=boss, role_code="admin_officer", org_unit_id=None
    )
    return boss


async def _signin(client, user):
    return await login(client, user, DEFAULT_TEST_PASSWORD)


@asynccontextmanager
async def _backdated(app_session, *specs):
    """Age claims' stay with FMS for the body of a test, then undo it.

    ``holder_since`` IS the hand-off instant while the state does not change —
    that is why R-7 added no column — and these rows are COMMITTED into a
    database the whole suite shares. A claim left aged 21 days is over the
    follow-up threshold forever, and every run adds more, until the
    ``external_over`` page is nothing but old test fixtures and the assertions
    below have stopped being about the claims they name.

    **R-9 made the undo structural rather than remembered.** The previous shape
    was a plain ``_backdate()`` whose docstring said *"every caller must undo
    this in a `finally`"* — and two callers did not, for three sessions, until
    54 permanently-aged rows pushed a freshly-aged claim off page 1 and failed
    an assertion that had been passing while testing nothing (#27). A docstring
    is not an enforcement mechanism. A context manager is: there is no way to
    take the aging without also taking the restore.

    Usage — ``async with _backdated(app_session, (claim, 21), (other, 12)):``
    """
    originals = [(claim, claim.holder_since) for claim, _ in specs]
    now = utc_now()
    for claim, days in specs:
        claim.holder_since = now - timedelta(days=days)
    await app_session.commit()
    try:
        yield
    finally:
        # Back to the present, not to the captured value: these claims are this
        # test's own and returning them to "just handed over" is what keeps them
        # out of every future run's follow-up filter.
        restore = utc_now()
        for claim, previous in originals:
            claim.holder_since = restore if previous is not None else None
        await app_session.commit()


# --- scope: the reason this endpoint is not just "My Work with filters" -----


async def test_a_plain_traveller_is_refused_not_shown_an_empty_list(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """The leak this endpoint exists to NOT have.

    ``staff`` holds ``reimb.claim.read`` globally (spec §3.2, so a traveller can
    read their own claim from anywhere in the tree). A list keyed on the route's
    permission would hand this user every claim in the agency. It is a 403, and
    deliberately not an empty 200: "there is no work" is a different and
    misleading statement from "this surface is not yours".
    """
    cast = await _at_fms(app_session, make_user)
    await app_session.commit()

    await _signin(client, cast.owner)
    refused = await client.get(f"{BASE}/claims")
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "reimb_queue_not_permitted"


async def test_a_scoped_overseer_never_sees_a_sibling_office(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """A scoped Admin Officer oversees their subtree and nothing beside it.
    Both claims are live, both sit at the same state, and only one is theirs."""
    mine = await _at_fms(app_session, make_user)
    theirs = await _at_fms(app_session, make_user)
    await app_session.commit()

    await _signin(client, mine.admin)
    body = (await client.get(f"{BASE}/claims")).json()
    ids = [item["id"] for item in body["items"]]
    assert mine.claim.id in ids
    assert theirs.claim.id not in ids


async def test_a_scoped_grant_reaches_down_the_whole_subtree(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """The grant is on the office; the claim belongs to a section two levels
    below. This is ``descendants_or_self`` doing its job through the endpoint."""
    cast = await standard_cast(app_session, make_user)
    section = await make_org_unit(
        app_session, kind="section", parent=cast.division
    )
    deep_staff = await make_staff(
        app_session, division_id=cast.division.id, section_id=section.id
    )
    deep_owner, _ = await make_user(roles=("staff",), staff_id=deep_staff.id)
    deep_claim = await trip_claim(
        app_session, staff=deep_staff, owner_user_id=deep_owner.id
    )
    await submit_claim(
        app_session, claim_id=deep_claim.id, actor_user_id=deep_owner.id
    )
    await app_session.commit()

    # cast.admin is admin_officer scoped at the OFFICE, two levels up.
    await _signin(client, cast.admin)
    body = (await client.get(f"{BASE}/claims")).json()
    assert deep_claim.id in [item["id"] for item in body["items"]]


async def test_a_global_grant_sees_every_office(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """Two claims in two unrelated offices, both visible to one unscoped grant.

    Aged well past anything else the shared test database holds so they land on
    the first page deterministically — the queue orders longest-waiting first,
    so a brand-new claim sorts last by design.
    """
    one = await _at_fms(app_session, make_user)
    two = await _at_fms(app_session, make_user)
    boss = await _global_admin(app_session, make_user)

    async with _backdated(app_session, (one.claim, 3650), (two.claim, 3649)):
        await _signin(client, boss)
        ids = [i["id"] for i in (await client.get(f"{BASE}/claims")).json()["items"]]
        assert one.claim.id in ids and two.claim.id in ids
        assert one.office.id != two.office.id


# --- membership: what a queue is, and is not -------------------------------


async def test_drafts_and_terminal_claims_are_absent(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """A draft is the traveller's own work (My Work has it) and a paid claim is
    finished — a queue is what is moving and stuck, not an archive. R-7-board's
    columns are where Done gets counted."""
    cast = await _at_fms(app_session, make_user)
    draft = await trip_claim(
        app_session, staff=cast.staff, owner_user_id=cast.owner.id
    )
    # R-7-events: the terminal rung records a payment reference, so a bare
    # `approve` no longer reaches it (workflow-standards §12).
    await record_payout(
        app_session,
        claim_id=cast.claim.id,
        actor_user_id=cast.admin.id,
        payout_ref="ADA-2026-00417",
        paid_on=to_manila(utc_now()).date(),
    )
    assert cast.claim.status == st.PAID_CLOSED
    await app_session.commit()

    await _signin(client, cast.admin)
    body = (await client.get(f"{BASE}/claims")).json()
    ids = [item["id"] for item in body["items"]]
    assert draft.id not in ids
    assert cast.claim.id not in ids


async def test_the_fms_held_claim_that_my_work_shows_nobody(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """The hole this increment exists to close, asserted from both ends in one
    test: the claim is in NOBODY's My Work, and it IS in the queue."""
    cast = await _at_fms(app_session, make_user)
    await app_session.commit()

    await _signin(client, cast.admin)
    work = (await client.get(f"{BASE}/my-work")).json()
    assert cast.claim.id not in [i["id"] for i in work["waiting_on_you"]]
    assert cast.claim.id not in [i["id"] for i in work["in_flight"]]

    item = next(
        i
        for i in (await client.get(f"{BASE}/claims")).json()["items"]
        if i["id"] == cast.claim.id
    )
    assert item["status"] == "handed_to_fms"
    assert item["holder_display"] == "FMS"
    assert item["next_action"] == "Waiting on FMS — update status"
    # The row says whose claim it is — My Work never has to.
    assert item["claimant_display"]


async def test_filters_narrow_by_kind_status_and_claimant(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    cast = await _at_fms(app_session, make_user)
    other = await trip_claim(
        app_session, staff=cast.staff, owner_user_id=cast.owner.id
    )
    await submit_claim(app_session, claim_id=other.id, actor_user_id=cast.owner.id)
    await app_session.commit()

    await _signin(client, cast.admin)
    at_fms = (await client.get(f"{BASE}/claims?status=handed_to_fms")).json()
    assert [i["id"] for i in at_fms["items"]] == [cast.claim.id]

    by_kind = (await client.get(f"{BASE}/claims?kind=liquidation")).json()
    assert by_kind["items"] == []

    mine = await client.get(f"{BASE}/claims?claimant_id={cast.staff.id}")
    assert {i["id"] for i in mine.json()["items"]} == {cast.claim.id, other.id}


# --- spec §7 rule 5: the >10 working day follow-up filter -------------------


async def test_the_threshold_boundary_is_exclusive(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """Spec §7 rule 5 says "> 10 working days", so ten is not yet late.

    Backdated in calendar days, which bracket the working-day count from both
    sides: 21 calendar days is at least 11 working days however the weekends
    fall, and 12 calendar days is at most 10.
    """
    late = await _at_fms(app_session, make_user)
    fresh = await _at_fms(app_session, make_user)
    boss = await _global_admin(app_session, make_user)
    async with _backdated(app_session, (late.claim, 21), (fresh.claim, 12)):
        await _signin(client, boss)
        # Scoped per claimant: the filter's page is shared with every other
        # externally-held claim in the database, and this assertion is about
        # these two.
        stale = await client.get(
            f"{BASE}/claims?external_over=true&claimant_id={late.staff.id}"
        )
        body = stale.json()
        assert [i["id"] for i in body["items"]] == [late.claim.id]
        assert body["followup_working_days"] == 10

        row = body["items"][0]
        assert row["days_with_fms"] > 10
        assert row["external_followup"] is True

        recent = await client.get(
            f"{BASE}/claims?external_over=true&claimant_id={fresh.staff.id}"
        )
        assert recent.json()["items"] == []


async def test_holidays_inside_the_window_shorten_the_count(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """The count is Manila WORKING days off the real calendar — the reason no
    browser may compute it (api-standards §9e).

    Measured as a DIFFERENCE across the same claim rather than against a
    hand-computed constant, so the assertion proves the holiday calendar is
    honoured without depending on which weekday the suite runs.
    """
    cast = await _at_fms(app_session, make_user)
    boss = await _global_admin(app_session, make_user)

    async with _backdated(app_session, (cast.claim, 14)):
        await _signin(client, boss)
        # Scoped per claimant: page 1 of the unfiltered queue is shared with
        # every other in-flight claim in the database.
        queue = f"{BASE}/claims?claimant_id={cast.staff.id}"

        def _days(body):
            return next(i for i in body["items"] if i["id"] == cast.claim.id)[
                "days_with_fms"
            ]

        before = _days((await client.get(queue)).json())
        assert before >= 2  # 14 calendar days always spans some working days

        token = uuid.uuid4().hex[:8]
        today = utc_now().date()
        # Skip days the seeded PH calendar already counts as non-working — a
        # duplicate holiday row would change nothing and the test would prove it.
        already = await load_nonworking_dates(
            app_session, today - timedelta(days=14), today
        )
        newly_closed = [
            day
            for day in (today - timedelta(days=offset) for offset in range(1, 14))
            if day.weekday() < 5 and day not in already
        ][:2]
        assert len(newly_closed) == 2, "no open working days left in the window"
        rows = [
            Holiday(
                calendar_date=day,
                name=f"Queue test holiday {token} {day}",
                holiday_type="special_non_working",
            )
            for day in newly_closed
        ]
        app_session.add_all(rows)
        await app_session.commit()

        try:
            after = _days((await client.get(queue)).json())
            assert after == before - len(newly_closed)
        finally:
            # These are holidays in the RECENT PAST, and the suite shares one
            # database: left behind, they would silently shorten every later
            # "working days since…" count in the whole codebase — including this
            # file's own follow-up threshold tests. Retired, not deleted (rule 6).
            for row in rows:
                row.is_active = False
                row.deleted_at = utc_now()
            await app_session.commit()


async def test_a_claim_still_in_the_bureau_has_no_fms_clock(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """``days_with_fms`` is null, not 0, when FMS does not hold the claim — 0
    is a false answer to a question that does not apply."""
    cast = await standard_cast(app_session, make_user)
    await submit_claim(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.owner.id
    )
    await app_session.commit()

    await _signin(client, cast.admin)
    row = next(
        i
        for i in (await client.get(f"{BASE}/claims")).json()["items"]
        if i["id"] == cast.claim.id
    )
    assert row["days_with_fms"] is None
    assert row["external_followup"] is False


async def test_stalled_claims_sort_above_longer_waiting_ones(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """Spec §7 rule 5: "anything Overdue sorts to top with the red badge".

    The in-bureau claim has waited LONGER, so the SQL's longest-waiting-first
    order puts it ahead; the urgency lift is what must override that. Its own
    gate SLA is freshly stamped, so it is on track and stays in the lower class.

    A year with FMS, not three weeks: the threshold is working days off a shared
    holiday calendar, and this test is about the ORDER, so it must not be able
    to fail because of how the calendar happened to fall.

    **Both claims are undone in a `finally`, and this test is why the rule
    exists.** It leaked for three sessions and then failed, from its own
    fixtures: every run left a 365-day and a 730-day claim behind, the queue
    pages at 50 in longest-waiting-first order, and once 54 permanently-aged
    rows had piled up the freshly-aged `stalled` fell off page 1 while the
    older `waiting` stayed — so `ours` came back with one id and the assertion
    was about the wrong set. The lift was working the whole time.
    """
    stalled = await _at_fms(app_session, make_user)
    waiting = await standard_cast(app_session, make_user)
    await submit_claim(
        app_session, claim_id=waiting.claim.id, actor_user_id=waiting.owner.id
    )
    boss = await _global_admin(app_session, make_user)

    async with _backdated(app_session, (stalled.claim, 365), (waiting.claim, 730)):
        await _signin(client, boss)
        items = (await client.get(f"{BASE}/claims")).json()["items"]
        ours = [i for i in items if i["id"] in (stalled.claim.id, waiting.claim.id)]
        # Both must be ON the page before the order means anything — otherwise a
        # one-element list trivially "matches" a prefix of the expected order.
        assert len(ours) == 2
        assert [i["id"] for i in ours] == [stalled.claim.id, waiting.claim.id]


async def test_the_total_counts_beyond_the_page(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """A queue that says "1 item" while hiding others is worse than no number."""
    cast = await _at_fms(app_session, make_user)
    second = await trip_claim(
        app_session, staff=cast.staff, owner_user_id=cast.owner.id
    )
    await submit_claim(app_session, claim_id=second.id, actor_user_id=cast.owner.id)
    await app_session.commit()

    await _signin(client, cast.admin)
    body = (await client.get(f"{BASE}/claims?limit=1")).json()
    assert len(body["items"]) == 1
    assert body["total"] >= 2
