"""R-7-board — the pipeline board (``GET /board``), spec §9.6.

R-7-queue made stuck work findable one row at a time and R-7-events made it
actionable. This surface answers the question a bureau chief asks from across
the room: **how much is where.** So the headline is a COUNT and a PESO TOTAL per
column, and spec §14 grades exactly one sentence on it — *"board totals match
DB"*. Most of this file is that sentence.

Three things are on trial.

**Scope, first, because it is the security half.** The board is a list with
headers, so api-standards §9f applies unchanged: it is keyed on the OVERSIGHT
permissions, never on the route's globally-granted ``reimb.claim.read``. The
leak would be worse here than on the queue — a queue leaks rows one page at a
time, a board leaks a division's whole budget in one integer.

**The columns are GROUPS of statuses.** ``services/status.py`` owns the grouping
per kind, and both kinds ride one board because a liquidation is work in the
same pipeline.

**The Done column is bounded and terminal.** Terminal because that is the trap
``queue.base_query`` was built to avoid (it excludes terminal claims — it is a
queue), and bounded because ``paid_closed``/``settled`` accumulate forever.

TEST HYGIENE. The suite shares one database, and a board is exactly the surface
where that bites: every other test's committed claims sit in these columns. So
**every assertion here is made through a SCOPED overseer**, whose office
``standard_cast`` created fresh for that test — which makes the counts and the
totals about this test's claims and nothing else. The two tests that genuinely
need a global grant assert membership, never a count. Anything that writes a
date relative to today undoes itself in a ``finally`` (sessions #24 and #25).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from office_connect.core.money import money_str
from office_connect.core.time import to_manila, utc_now
from office_connect.modules.reimbursement.models import ReimbClaim
from office_connect.modules.reimbursement.services import queue
from office_connect.modules.reimbursement.services import status as st
from office_connect.modules.reimbursement.services.external import record_payout
from office_connect.modules.reimbursement.services.lifecycle import (
    claim_action,
    submit_claim,
)
from tests.conftest import DEFAULT_TEST_PASSWORD, login
from tests.reimb_lifecycle_helpers import (
    return_reason_ids,
    standard_cast,
    trip_claim,
)
from tests.workflow_helpers import grant_scoped_role

BASE = "/api/v1/reimbursement"

#: The fixture trip's grand total — ₱6,500 (manila_3day + two ₱500 fares).
TRIP = Decimal("6500.00")


async def _signin(client, user):
    return await login(client, user, DEFAULT_TEST_PASSWORD)


async def _submitted(app_session, make_user, **cast_kw):
    """The standard cast with its claim submitted — ``division_approval``,
    which is In Bureau."""
    cast = await standard_cast(app_session, make_user, **cast_kw)
    await submit_claim(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.owner.id
    )
    return cast


async def _at_fms(app_session, make_user, **cast_kw):
    """…driven the two rungs to ``handed_to_fms`` — the With FMS column."""
    cast = await _submitted(app_session, make_user, **cast_kw)
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


async def _paid(app_session, make_user, **cast_kw):
    """…and closed. The Done column, and the trap: ``base_query`` excludes
    exactly this claim, because it is a queue."""
    cast = await _at_fms(app_session, make_user, **cast_kw)
    await record_payout(
        app_session,
        claim_id=cast.claim.id,
        actor_user_id=cast.admin.id,
        payout_ref="ADA-2026-00931",
        paid_on=to_manila(utc_now()).date(),
    )
    assert cast.claim.status == st.PAID_CLOSED
    return cast


async def _settled_liquidation(app_session, make_user):
    """A liquidation walked its own chain to ``settled`` — the OTHER kind's Done.

    An exact-match advance (₱6,500 against the ₱6,500 fixture trip) so neither
    of spec §6.2's side-steps fires and the test stays about the board. The
    certify_c approval carries a comment because that rung records a wet
    signature and the transition requires one.
    """
    from office_connect.modules.reimbursement.services import cash_advance as ca
    from office_connect.modules.reimbursement.services import liquidation as liq
    from office_connect.modules.reimbursement.services import settlement
    from tests.reimb_checklist_helpers import satisfy_packet
    from tests.reimb_lifecycle_helpers import JUL1, JUL3, ensure_reimb_workflow
    from tests.reimbursement_helpers import make_leg

    cast = await standard_cast(app_session, make_user)
    await ensure_reimb_workflow(app_session)
    cast.advance = await ca.create_cash_advance(
        app_session,
        claimant_id=cast.staff.id,
        amount=TRIP,
        actor_user_id=cast.admin.id,
        dv_no="DV-2026-0311",
        dv_date=date(2026, 6, 25),
        dpo_no="DPO-2026-0311",
        date_return=JUL3,
    )
    claim = await liq.start_liquidation(
        app_session, cash_advance_id=cast.advance.id, actor_user_id=cast.owner.id
    )
    claim.date_depart = JUL1
    claim.destination_region_code = "13"
    await make_leg(
        app_session, claim_id=claim.id, seq=1, leg_date=JUL1,
        destination_region_code="13", transport_mode="bus", fare="500.00",
    )
    await make_leg(
        app_session, claim_id=claim.id, seq=2, leg_date=JUL3,
        transport_mode="bus", fare="500.00",
    )
    await satisfy_packet(app_session, claim=claim, actor_user_id=cast.owner.id)
    await app_session.flush()

    await submit_claim(app_session, claim_id=claim.id, actor_user_id=cast.owner.id)
    await claim_action(
        app_session, claim_id=claim.id, action="approve",
        actor_user_id=cast.approver.id,
    )
    await claim_action(
        app_session, claim_id=claim.id, action="approve",
        actor_user_id=cast.admin.id, comment="Wet signature recorded.",
    )
    await settlement.record_settlement(
        app_session, claim_id=claim.id, actor_user_id=cast.admin.id
    )
    assert claim.status == st.SETTLED
    cast.claim = claim
    return cast


async def _extra_claim(app_session, cast):
    """Another submitted claim for the same claimant, in the same office."""
    claim = await trip_claim(
        app_session, staff=cast.staff, owner_user_id=cast.owner.id
    )
    await submit_claim(app_session, claim_id=claim.id, actor_user_id=cast.owner.id)
    return claim


async def _board(client):
    response = await client.get(f"{BASE}/board")
    assert response.status_code == 200, response.text
    return response.json()


def _column(body, key):
    column = next(c for c in body["columns"] if c["key"] == key)
    return column


def _ids(body, key):
    return [item["id"] for item in _column(body, key)["items"]]


# --- scope: a board leaks a whole budget in one integer ---------------------


async def test_a_plain_traveller_is_refused_not_shown_an_empty_board(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """§9f, and it matters more here than on the queue. ``staff`` holds
    ``reimb.claim.read`` GLOBALLY so a traveller can read their own claim, so a
    board keyed on the route's permission would show every employee the agency's
    entire pipeline as three peso totals — no paging, no scrolling, one glance.

    403, not ``200`` with empty columns: "₱0.00 is in flight" is a false
    statement about the world, where the truth is "this surface is not yours".
    The refusal is the queue's own sentence, which already names My Work.
    """
    cast = await _at_fms(app_session, make_user)
    await app_session.commit()

    await _signin(client, cast.owner)
    refused = await client.get(f"{BASE}/board")
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "reimb_queue_not_permitted"


async def test_a_scoped_overseer_never_counts_a_sibling_office(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """The failure mode this test exists for is subtler than a wrong card list:
    cards scoped correctly while the HEADER aggregates the whole agency. The
    count and the total are what a director reads, so both are asserted."""
    mine = await _at_fms(app_session, make_user)
    theirs = await _at_fms(app_session, make_user)
    assert mine.office.id != theirs.office.id
    await app_session.commit()

    await _signin(client, mine.admin)
    body = await _board(client)
    with_fms = _column(body, st.WITH_FMS)

    assert mine.claim.id in _ids(body, st.WITH_FMS)
    assert theirs.claim.id not in _ids(body, st.WITH_FMS)
    # One claim in this office, so the header is exactly one trip — not two.
    assert with_fms["count"] == 1
    assert with_fms["total"] == money_str(TRIP)


async def test_a_global_grant_sees_every_office(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """Membership only — a global board spans the shared test database, so a
    count here would be a number about every other test in the suite."""
    one = await _at_fms(app_session, make_user)
    two = await _at_fms(app_session, make_user)
    boss, _ = await make_user()
    await grant_scoped_role(
        app_session, user=boss, role_code="admin_officer", org_unit_id=None
    )
    await app_session.commit()

    await _signin(client, boss)
    body = await _board(client)
    assert _column(body, st.WITH_FMS)["count"] >= 2
    assert one.office.id != two.office.id


# --- the columns are status GROUPS, not statuses ---------------------------


async def test_the_three_columns_are_status_groups(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """Spec §9.2: "Columns = status groups (In Bureau / With FMS / Done)".

    ``division_approval`` and ``returned`` are different statuses that share a
    column, which is the whole point — a chief does not want five columns, they
    want to know whether the packet has left the building.
    """
    cast = await _submitted(app_session, make_user)
    returned = await _extra_claim(app_session, cast)
    await claim_action(
        app_session, claim_id=returned.id, action="return",
        actor_user_id=cast.approver.id, comment="Fix the itinerary.",
        reason_ids=await return_reason_ids(app_session),
    )
    assert returned.status == st.RETURNED
    await app_session.commit()

    await _signin(client, cast.admin)
    body = await _board(client)
    in_bureau = _ids(body, st.IN_BUREAU)
    assert cast.claim.id in in_bureau
    assert returned.id in in_bureau
    assert _column(body, st.IN_BUREAU)["count"] == 2
    assert [c["key"] for c in body["columns"]] == [
        st.IN_BUREAU, st.WITH_FMS, st.BOARD_DONE
    ]
    assert [c["label"] for c in body["columns"]] == ["In Bureau", "With FMS", "Done"]


async def test_drafts_and_cancelled_claims_are_on_no_column(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """A draft is nobody's oversight (My Work has it, and the instance join
    excludes it by construction). ``cancelled`` is spec §6.1 row 9's "excluded
    from KPIs": a voided claim produced no disbursement, so counting its ₱6,500
    would inflate a total with money that never moved.

    Both are asserted on the COUNT as well as the cards — a claim that vanished
    from the cards but survived in the header would be the exact defect this
    surface cannot afford.
    """
    cast = await _submitted(app_session, make_user)
    draft = await trip_claim(
        app_session, staff=cast.staff, owner_user_id=cast.owner.id
    )
    # `cancel` is legal from `draft` and `returned` only (workflow.py), and a
    # draft has no instance — so the only cancelled claim that could ever reach
    # a board is one returned first. That is the row this test needs.
    cancelled = await _extra_claim(app_session, cast)
    await claim_action(
        app_session, claim_id=cancelled.id, action="return",
        actor_user_id=cast.approver.id, comment="Missing receipts.",
        reason_ids=await return_reason_ids(app_session),
    )
    await claim_action(
        app_session, claim_id=cancelled.id, action="cancel",
        actor_user_id=cast.owner.id, comment="Trip called off.",
    )
    assert cancelled.status == st.CANCELLED
    await app_session.commit()

    await _signin(client, cast.admin)
    body = await _board(client)
    every_id = [i for column in body["columns"] for i in _ids(body, column["key"])]
    assert draft.id not in every_id
    assert cancelled.id not in every_id
    # Only the one submitted claim is counted anywhere on this office's board.
    assert sum(c["count"] for c in body["columns"]) == 1
    assert _column(body, st.IN_BUREAU)["total"] == money_str(TRIP)


# --- the trap: Done is what the queue excludes ------------------------------


async def test_the_done_column_holds_what_the_queue_excludes(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """``queue.base_query`` drops terminal claims because it is a queue, and its
    docstring has said since R-7-queue that "R-7-board's columns are where Done
    gets counted". Both ends are asserted in one test, so a change that widened
    the queue to make the board work would fail here rather than pass twice."""
    cast = await _paid(app_session, make_user)
    await app_session.commit()

    await _signin(client, cast.admin)
    body = await _board(client)
    assert cast.claim.id in _ids(body, st.BOARD_DONE)
    assert _column(body, st.BOARD_DONE)["count"] == 1
    assert _column(body, st.BOARD_DONE)["total"] == money_str(TRIP)

    queued = (await client.get(f"{BASE}/claims")).json()
    assert cast.claim.id not in [i["id"] for i in queued["items"]]


async def test_the_terminal_flag_is_opt_in_not_the_default(
    make_user, seed_rbac, app_session, reimb_flag_on
):
    """At the service level, both directions. The board opts out of the terminal
    exclusion by typing ``include_terminal=True``; nothing widens by omission,
    which is why this is a keyword with a safe default rather than a second
    query builder holding a second copy of the scope clause."""
    cast = await _paid(app_session, make_user)
    await app_session.flush()

    scope = dict(is_global=False, unit_ids={cast.office.id, cast.division.id})

    default = (
        (await app_session.execute(queue.base_query(**scope))).scalars().all()
    )
    assert cast.claim.id not in [c.id for c in default]

    widened = (
        (
            await app_session.execute(
                queue.base_query(**scope, include_terminal=True)
            )
        )
        .scalars()
        .all()
    )
    assert cast.claim.id in [c.id for c in widened]
    await app_session.rollback()


async def test_a_settled_liquidation_lands_in_done_beside_a_paid_claim(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """Both kinds ride ONE board. A liquidation is work in the same pipeline,
    and forking the board by kind would ask a chief to read two boards to answer
    one question. ``settled`` is the liquidation's ``paid_closed`` — a different
    code, a different chain, the same column."""
    cast = await _settled_liquidation(app_session, make_user)
    await app_session.commit()

    await _signin(client, cast.admin)
    body = await _board(client)
    assert cast.claim.kind == st.LIQUIDATION_KIND
    assert cast.claim.status == st.SETTLED
    assert cast.claim.id in _ids(body, st.BOARD_DONE)
    assert _column(body, st.BOARD_DONE)["count"] == 1
    assert _column(body, st.BOARD_DONE)["total"] == money_str(TRIP)
    # Its card carries the liquidation vocabulary's label, not the claim's.
    card = next(
        c for c in _column(body, st.BOARD_DONE)["items"] if c["id"] == cast.claim.id
    )
    assert card["status_label"] == "Settled"


# --- the money: spec §14's "board totals match DB" -------------------------


async def test_the_column_total_is_the_sum_of_its_claims(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """Server-computed, summed in SQL, crossing as a 2-dp STRING like every
    other money value. Three ₱6,500 trips are ₱19,500 — asserted against
    ``money_str`` rather than a literal, so the canonical serialization is what
    is on trial and not a hand-typed copy of it."""
    cast = await _submitted(app_session, make_user)
    await _extra_claim(app_session, cast)
    await _extra_claim(app_session, cast)
    await app_session.commit()

    await _signin(client, cast.admin)
    in_bureau = _column(await _board(client), st.IN_BUREAU)
    assert in_bureau["count"] == 3
    assert in_bureau["total"] == money_str(TRIP * 3)
    assert in_bureau["total"] == "19500.00"


async def test_an_empty_column_totals_zero_pesos_not_null(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """An empty column is a fact, not a gap. ``"0.00"`` — never null, never a
    JSON number — so the header renders ₱0.00 rather than blank or NaN."""
    cast = await _submitted(app_session, make_user)
    await app_session.commit()

    await _signin(client, cast.admin)
    body = await _board(client)
    for key in (st.WITH_FMS, st.BOARD_DONE):
        assert _column(body, key)["count"] == 0
        assert _column(body, key)["items"] == []
        assert _column(body, key)["total"] == "0.00"


async def test_the_total_counts_past_the_card_cap(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """**The most important test in this file — it is the difference between a
    board and a lie.**

    The cards are capped at ``BOARD_CARD_LIMIT``; the header is not. A count and
    a total computed from the visible page would silently under-report the
    bureau's exposure by however much did not fit on screen, and would look
    entirely correct while doing it. So the header is a SQL aggregate over the
    whole column, and ``card_limit`` rides the response so the client can say
    what it is hiding.
    """
    cast = await _submitted(app_session, make_user)
    extra = queue.BOARD_CARD_LIMIT + 1  # one more than fits, plus the cast's own
    for _ in range(extra):
        await _extra_claim(app_session, cast)
    await app_session.commit()

    await _signin(client, cast.admin)
    body = await _board(client)
    in_bureau = _column(body, st.IN_BUREAU)

    assert len(in_bureau["items"]) == queue.BOARD_CARD_LIMIT
    assert in_bureau["count"] == extra + 1
    assert in_bureau["count"] > len(in_bureau["items"])
    assert in_bureau["total"] == money_str(TRIP * (extra + 1))
    assert body["card_limit"] == queue.BOARD_CARD_LIMIT


async def test_a_soft_deleted_claim_leaves_the_column_and_the_total(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """Rule 6 reaching an AGGREGATE. ``with_loader_criteria`` covers a
    ``with_only_columns`` select built from an ORM query — but it would NOT
    cover a rewrite to ``text()`` or a Core table (core/soft_delete.py's own
    documented caveat), and that rewrite is exactly the kind of thing a
    performance pass does to an aggregate. This test is what would catch it."""
    cast = await _submitted(app_session, make_user)
    doomed = await _extra_claim(app_session, cast)
    await app_session.commit()

    await _signin(client, cast.admin)
    before = _column(await _board(client), st.IN_BUREAU)
    assert before["count"] == 2 and before["total"] == money_str(TRIP * 2)

    from office_connect.core.soft_delete import soft_delete

    soft_delete(doomed, actor_id=cast.admin.id)
    await app_session.commit()

    after = _column(await _board(client), st.IN_BUREAU)
    assert after["count"] == 1
    assert after["total"] == money_str(TRIP)
    assert doomed.id not in _ids(await _board(client), st.IN_BUREAU)


# --- the Done window -------------------------------------------------------


async def test_done_covers_a_recent_window_not_all_time(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """``paid_closed`` and ``settled`` accumulate forever, and an all-time peso
    figure stops saying anything about how the bureau is doing — by year two it
    is a number nobody reads. So Done looks back ``board.done_window_days``.

    The claim closed long ago must leave the CARDS, the COUNT and the TOTAL
    together; dropping it from one and not the others is how a header starts
    describing a set the cards are not from.

    ``updated_at`` is the window's field because a terminal claim is read-only —
    no amendment route — so its ``updated_at`` IS the closing instant, and it is
    the one field that means that on both kinds.
    """
    recent = await _paid(app_session, make_user)
    old = await _paid(app_session, make_user)
    # Two casts, so two offices and two scoped boards — which is what lets each
    # assertion below be an absolute count rather than a delta against whatever
    # else the shared database holds.
    old_claim = old.claim
    await app_session.commit()

    # Age the old one past the window. Committed, so it undoes itself below.
    aged = utc_now() - timedelta(days=queue.DONE_WINDOW_DEFAULT + 30)
    original = old_claim.updated_at
    try:
        old_claim.updated_at = aged
        await app_session.commit()

        await _signin(client, recent.admin)
        mine = _column(await _board(client), st.BOARD_DONE)
        assert recent.claim.id in _ids(await _board(client), st.BOARD_DONE)
        assert mine["count"] == 1
        assert mine["total"] == money_str(TRIP)

        await _signin(client, old.admin)
        theirs = _column(await _board(client), st.BOARD_DONE)
        assert old_claim.id not in _ids(await _board(client), st.BOARD_DONE)
        assert theirs["count"] == 0
        assert theirs["total"] == "0.00"
    finally:
        old_claim.updated_at = original
        await app_session.commit()


async def test_the_window_is_config_and_fails_soft(
    make_user, seed_rbac, app_session, reimb_flag_on
):
    """A missing config row must not blank a column — the same fail-soft rule
    every other cadence value follows (a display window is a nudge, not money).
    The seeded value and the code default agree, which is what makes the
    fallback invisible in practice and worth asserting explicitly."""
    assert await queue.done_window_days(app_session) == queue.DONE_WINDOW_DEFAULT
    assert queue.DONE_WINDOW_DEFAULT == 90
    now = utc_now()
    assert queue.done_cutoff(now, 90) == now - timedelta(days=90)


async def test_only_terminal_rows_are_age_filtered(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """In Bureau and With FMS are UNBOUNDED, deliberately. A claim stuck since
    March is precisely what the board exists to show — ageing it off the board
    would hide the one thing spec §7 rule 5 calls non-negotiable."""
    cast = await _at_fms(app_session, make_user)
    original = cast.claim.updated_at
    try:
        cast.claim.updated_at = utc_now() - timedelta(days=400)
        await app_session.commit()

        await _signin(client, cast.admin)
        body = await _board(client)
        assert cast.claim.id in _ids(body, st.WITH_FMS)
        assert _column(body, st.WITH_FMS)["count"] == 1
    finally:
        cast.claim.updated_at = original
        await app_session.commit()


# --- ordering: spec §9.6's "overdue cards float to top" --------------------


async def test_stalled_cards_float_to_the_top_of_their_column(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """Spec §9.6. Aged 400 days rather than 21 so the Manila working-day
    calendar cannot decide the outcome — the assertion is about the SORT, and a
    fixture that sits near the threshold would make it about the holiday table.

    Undone in a ``finally``: the suite shares one database and a claim left aged
    is over the follow-up threshold forever (session #24's disease).
    """
    stalled = await _at_fms(app_session, make_user)
    fresh = await _extra_claim(app_session, stalled)
    await claim_action(
        app_session, claim_id=fresh.id, action="approve",
        actor_user_id=stalled.approver.id,
    )
    await claim_action(
        app_session, claim_id=fresh.id, action="approve",
        actor_user_id=stalled.admin.id,
    )
    assert fresh.status == st.HANDED_TO_FMS
    await app_session.commit()

    try:
        stalled.claim.holder_since = utc_now() - timedelta(days=400)
        await app_session.commit()

        await _signin(client, stalled.admin)
        body = await _board(client)
        cards = _column(body, st.WITH_FMS)["items"]
        assert [c["id"] for c in cards] == [stalled.claim.id, fresh.id]
        assert cards[0]["external_followup"] is True
        assert cards[1]["external_followup"] is False
    finally:
        now = utc_now()
        stalled.claim.holder_since = now
        fresh.holder_since = now
        await app_session.commit()


async def test_the_done_column_leads_with_the_most_recently_finished(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """A terminal state CLEARS the holder, so ``holder_since`` is null on every
    Done row and "longest waiting" is not merely wrong there — it is undefined,
    and every row would tie and fall through to ``id``. What a Done column is
    asked is "what just finished"."""
    cast = await _paid(app_session, make_user)
    second = await _extra_claim(app_session, cast)
    await claim_action(
        app_session, claim_id=second.id, action="approve",
        actor_user_id=cast.approver.id,
    )
    await claim_action(
        app_session, claim_id=second.id, action="approve",
        actor_user_id=cast.admin.id,
    )
    await record_payout(
        app_session, claim_id=second.id, actor_user_id=cast.admin.id,
        payout_ref="ADA-2026-00932", paid_on=to_manila(utc_now()).date(),
    )
    await app_session.commit()

    assert cast.claim.holder_since is None
    await _signin(client, cast.admin)
    body = await _board(client)
    # `second` closed last, so it leads.
    assert _ids(body, st.BOARD_DONE) == [second.id, cast.claim.id]
    assert _column(body, st.BOARD_DONE)["count"] == 2


# --- routing + the envelope ------------------------------------------------


async def test_the_board_has_its_own_path_not_a_literal_under_claims(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """Why the route is ``/board``. ``claims.router`` is included first and
    declares ``GET /claims/{claim_id}``, which FastAPI matches in registration
    order — so ``/claims/board`` is read as a claim id and 422s. Making that URL
    work would mean pinning router include order, a dependency nothing in the
    codebase declares and a future alphabetization would silently break.

    Pinned rather than merely avoided, so the reason survives the decision.
    """
    cast = await _submitted(app_session, make_user)
    await app_session.commit()

    await _signin(client, cast.admin)
    assert (await client.get(f"{BASE}/board")).status_code == 200
    assert (await client.get(f"{BASE}/claims/board")).status_code == 422


async def test_the_envelope_states_what_the_cards_hide(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """§9f's "state what the page is hiding", second instance. The cap and the
    window ride the response so the client quotes the SERVER's numbers — a
    literal in the browser is one more thing to keep in step, and the day it
    drifts the page says "showing 20 of 137" while showing 50."""
    cast = await _submitted(app_session, make_user)
    await app_session.commit()

    await _signin(client, cast.admin)
    body = await _board(client)
    assert body["card_limit"] == queue.BOARD_CARD_LIMIT
    assert body["done_window_days"] == queue.DONE_WINDOW_DEFAULT
    assert body["followup_working_days"] >= 1
    assert len(body["columns"]) == 3


async def test_a_board_card_carries_what_a_card_renders(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """Spec §9.2: cards show ref, name, ₱ and days-in-state. The row is
    ``QueueItemOut`` unchanged — a third row shape for a third lens is how two
    lists drift apart (delta row 140), so the board reuses the queue's."""
    cast = await _at_fms(app_session, make_user)
    await app_session.commit()

    await _signin(client, cast.admin)
    card = _column(await _board(client), st.WITH_FMS)["items"][0]
    assert card["ref_no"]
    assert card["claimant_display"]
    assert card["grand"] == money_str(TRIP)
    assert card["status"] == st.HANDED_TO_FMS
    assert card["status_label"] == "Handed to FMS"
    assert card["days_with_fms"] is not None
    assert card["days_in_state"] >= 0


async def test_a_done_card_has_no_holder_and_no_clock(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """The reason the board composes its own meta line. A terminal claim has no
    holder and no ``holder_since``, so ``days_in_state`` is 0 — and a card that
    reused the queue's wording would print "0 days in this step" on a claim paid
    three weeks ago, a false statement the queue never had to make because a
    queue has no terminal rows."""
    cast = await _paid(app_session, make_user)
    await app_session.commit()

    await _signin(client, cast.admin)
    card = _column(await _board(client), st.BOARD_DONE)["items"][0]
    assert card["holder_kind"] is None
    assert card["holder_since"] is None
    assert card["days_in_state"] == 0
    assert card["days_with_fms"] is None
    assert card["next_action"] is None
    # `updated_at` is what the card must date itself from instead.
    assert card["updated_at"]


async def test_the_seeded_window_matches_the_code_default(
    app_session, seed_rbac, reimb_flag_on
):
    """The config pack and the fallback must agree, or the board silently
    changes shape the first time somebody runs the seeds.

    (The flag-OFF→404 case lives in ``test_reimb_api_flag_gate.py``, beside the
    fixture that owns the flag's prior state — one place restores it.)
    """
    from office_connect.modules.reimbursement.seeds import REIMB_CONFIGS

    row = next(r for r in REIMB_CONFIGS.rows if r["key"] == queue.DONE_WINDOW_KEY)
    assert row["value"]["days"] == queue.DONE_WINDOW_DEFAULT
    assert isinstance(row["effective_from"], date)
