"""R-8 — Insights + the comment-learning loop (spec §11), and its two graded lines.

Spec §14's R-8 row grades exactly two sentences: *"Promotion creates a working
warning with no deploy; aggregates only."* Most of this file is those two.

**"Aggregates only"** is tested from three directions, because it fails in three
different ways. The response has no person dimension at all (there is nothing to
assert about a claimant field that does not exist, so what is asserted is the
403 and the scope). The count spans only the actor's own subtree. And a plain
traveller is REFUSED rather than shown an empty ranking, because "no claim comes
back for any reason" is a false statement about the world.

**"No deploy"** is one test with a promote, a re-read of the taxonomy the wizard
uses, and a demote — the whole wire from the Admin Officer's click to the
claimant's warning, with nothing in between but a boolean.

TEST HYGIENE, and there is a NEW instance of it here.

1. Every count assertion is made through a **scoped overseer** whose office
   ``standard_cast`` created fresh (the R-7-board rule). The suite shares one
   database and every other test's returns are real return events; a global
   actor could only ever assert membership.
2. Anything dated relative to today undoes itself — except that here it cannot
   be undone, because ``reimb_return_events`` REVOKEs UPDATE from ``oc_app``
   (``test_append_only.py`` pins that). So a windowed event is **INSERTed with
   an explicit ``created_at``** rather than written and then backdated, and the
   scoped overseer is what keeps it out of everyone else's numbers.
3. **NEW: a promotion mutates a SHARED SEEDED ROW.** It is tenant-wide by
   design, so a test that promotes and does not demote leaves a warning standing
   for every later test — and for the next developer's dev database.
   ``_promoted`` is a context manager for exactly that reason, and
   ``test_reimbursement_seeds.py``'s "nothing ships promoted" assertion is the
   canary that catches a leak.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import timedelta

from sqlalchemy import select

from office_connect.core.models import AuditLog
from office_connect.core.time import to_manila, utc_now
from office_connect.modules.reimbursement.models import (
    ReimbReturnEvent,
    ReimbReturnReasonCatalog,
)
from office_connect.modules.reimbursement.services import insights
from office_connect.modules.reimbursement.services import status as st
from office_connect.modules.reimbursement.services.lifecycle import (
    claim_action,
    submit_claim,
)
from tests.conftest import CSRF, DEFAULT_TEST_PASSWORD, login
from tests.reimb_lifecycle_helpers import (
    return_reason_ids,
    standard_cast,
    trip_claim,
)
from tests.workflow_helpers import grant_scoped_role

BASE = "/api/v1/reimbursement"
RANKING = f"{BASE}/insights/return-reasons"


async def _signin(client, user):
    return await login(client, user, DEFAULT_TEST_PASSWORD)


async def _returned(app_session, make_user, *codes: str, cast=None):
    """A claim submitted and then genuinely RETURNED through ``claim_action``.

    Deliberately the real path rather than a hand-written event row: the whole
    premise of the learning loop is that returns already record their reasons,
    and a test that inserted its own would be asserting against a fixture rather
    than against the module.
    """
    cast = cast or await standard_cast(app_session, make_user)
    claim = cast.claim
    if claim.workflow_instance_id is None:
        await submit_claim(
            app_session, claim_id=claim.id, actor_user_id=cast.owner.id
        )
    await claim_action(
        app_session,
        claim_id=claim.id,
        action="return",
        actor_user_id=cast.approver.id,
        comment="Fix the packet.",
        reason_ids=await return_reason_ids(app_session, *(codes or ("MISSING_OR",))),
    )
    assert claim.status == st.RETURNED
    return cast


async def _extra_returned(app_session, cast, *codes: str):
    """A SECOND claim for the same claimant, submitted and returned."""
    claim = await trip_claim(
        app_session, staff=cast.staff, owner_user_id=cast.owner.id
    )
    await submit_claim(app_session, claim_id=claim.id, actor_user_id=cast.owner.id)
    await claim_action(
        app_session,
        claim_id=claim.id,
        action="return",
        actor_user_id=cast.approver.id,
        comment="Fix the packet.",
        reason_ids=await return_reason_ids(app_session, *(codes or ("MISSING_OR",))),
    )
    return claim


async def _aged_return(app_session, *, claim, reason_ids, days_ago, actor_user_id):
    """A return event dated ``days_ago``, INSERTed rather than backdated.

    ``reimb_return_events`` is append-only with UPDATE revoked from ``oc_app``,
    so there is no way to move an existing row's ``created_at`` — which is the
    right design and simply means a window test writes its own row. The insert
    still hash-chains, and the row is on a claim inside the fixture's own fresh
    office, so it is invisible to every other test's scoped assertions.
    """
    event = ReimbReturnEvent(
        claim_id=claim.id,
        reason_ids=list(reason_ids),
        free_comment="Aged fixture row.",
        returned_to="claimant",
        created_at=utc_now() - timedelta(days=days_ago),
        created_by=actor_user_id,
    )
    app_session.add(event)
    await app_session.flush()
    return event


@asynccontextmanager
async def _promoted(app_session, code: str):
    """Promote a seeded reason for the body of a test, then put it back.

    The undo is mandatory, not tidy: ``reimb_return_reason_catalogs`` is
    tenant-wide seed data shared by the whole suite, so a leaked promotion is a
    warning every later test's wizard would carry — the same class of bug as the
    aged claims that leaked for three sessions at #24-#26, wearing a new coat.
    """
    row = (
        await app_session.execute(
            select(ReimbReturnReasonCatalog).where(
                ReimbReturnReasonCatalog.code == code
            )
        )
    ).scalar_one()
    before = row.promoted_check
    row.promoted_check = True
    await app_session.commit()
    try:
        yield row
    finally:
        row.promoted_check = before
        await app_session.commit()


async def _ranking(client):
    response = await client.get(RANKING)
    assert response.status_code == 200, response.text
    return response.json()


def _row(body, code):
    return next((item for item in body["items"] if item["code"] == code), None)


# --- the ranking (spec §11) -------------------------------------------------


async def test_reasons_rank_by_count_inside_the_window(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """The surface's one job: which reasons bring packets back, most first.

    Counts are absolute here and that is safe for exactly one reason — the
    actor is scoped to an office ``standard_cast`` created for this test, so
    the aggregate is about these three returns and nothing else in the database.
    """
    cast = await _returned(app_session, make_user, "MISSING_OR")
    await _extra_returned(app_session, cast, "MISSING_OR")
    await _extra_returned(app_session, cast, "UNSIGNED")
    await app_session.commit()

    await _signin(client, cast.admin)
    body = await _ranking(client)

    codes = [item["code"] for item in body["items"]]
    assert codes[:2] == ["MISSING_OR", "UNSIGNED"]
    assert _row(body, "MISSING_OR")["count"] == 2
    assert _row(body, "UNSIGNED")["count"] == 1
    assert _row(body, "MISSING_OR")["label"] == "Missing official receipt"


async def test_one_return_citing_three_reasons_is_one_return(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """Two true numbers that answer different questions, and the header must
    take the second: a return citing three reasons contributes 1 to each ranked
    row but is still ONE packet that came back. Summing the ranked counts into
    the header would inflate "37 returns" to "58" and nobody could reconcile it.
    """
    cast = await _returned(
        app_session, make_user, "MISSING_OR", "UNSIGNED", "PER_DIEM_CALC"
    )
    await app_session.commit()

    await _signin(client, cast.admin)
    body = await _ranking(client)

    assert body["total_returns"] == 1
    assert sum(item["count"] for item in body["items"]) == 3


async def test_the_window_and_its_period_start_come_from_the_server(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """api-standards §9g: a bound the client cannot see is a bound the client
    will eventually contradict. The header says "since <date>", and both halves
    of that sentence are the server's."""
    cast = await _returned(app_session, make_user)
    await app_session.commit()

    await _signin(client, cast.admin)
    body = await _ranking(client)

    assert body["window_days"] == insights.WINDOW_DEFAULT
    expected = to_manila(utc_now() - timedelta(days=insights.WINDOW_DEFAULT)).date()
    assert body["period_start"] == expected.isoformat()


async def test_a_return_outside_both_windows_is_not_counted(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """A 90-day ranking that quietly included year-old returns would describe a
    bureau that no longer exists."""
    cast = await standard_cast(app_session, make_user)
    await submit_claim(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.owner.id
    )
    await _aged_return(
        app_session,
        claim=cast.claim,
        reason_ids=await return_reason_ids(app_session, "OBSOLETE_FORM"),
        days_ago=insights.WINDOW_DEFAULT * 2 + 5,
        actor_user_id=cast.approver.id,
    )
    await app_session.commit()

    await _signin(client, cast.admin)
    body = await _ranking(client)

    assert _row(body, "OBSOLETE_FORM") is None
    assert body["total_returns"] == 0


# --- trend ------------------------------------------------------------------


async def test_trend_compares_against_the_immediately_preceding_window(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """Two returns this period against one in the last: ``up``, from 1.

    Both windows come off ONE grouped statement — two round-trips would let a
    return landing between them be counted in neither, which on a surface whose
    only job is counting is a wrong answer, not a rounding error.
    """
    cast = await _returned(app_session, make_user, "FARE_CLASS")
    await _extra_returned(app_session, cast, "FARE_CLASS")
    await _aged_return(
        app_session,
        claim=cast.claim,
        reason_ids=await return_reason_ids(app_session, "FARE_CLASS"),
        days_ago=insights.WINDOW_DEFAULT + 10,
        actor_user_id=cast.approver.id,
    )
    await app_session.commit()

    await _signin(client, cast.admin)
    row = _row(await _ranking(client), "FARE_CLASS")

    assert (row["count"], row["prior_count"], row["trend"]) == (2, 1, insights.UP)


async def test_a_first_appearance_is_new_not_up(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """"3 returns, up from 0" reads as a trend line when it is a debut. The two
    want different copy, so they are different verdicts."""
    cast = await _returned(app_session, make_user, "LATE_LIQUIDATION")
    await app_session.commit()

    await _signin(client, cast.admin)
    row = _row(await _ranking(client), "LATE_LIQUIDATION")

    assert (row["count"], row["prior_count"], row["trend"]) == (1, 0, insights.NEW)


async def test_a_reason_that_fell_to_zero_is_still_listed_as_down(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """The row that proves the loop WORKED, on the one surface built to show it.

    A reason with returns last period and none this one is the whole payoff of a
    promotion. Dropping it because its current count is 0 would delete the only
    evidence anything improved, so it is kept and sorts last.
    """
    cast = await standard_cast(app_session, make_user)
    await submit_claim(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.owner.id
    )
    await _aged_return(
        app_session,
        claim=cast.claim,
        reason_ids=await return_reason_ids(app_session, "OBSOLETE_FORM"),
        days_ago=insights.WINDOW_DEFAULT + 10,
        actor_user_id=cast.approver.id,
    )
    await app_session.commit()

    await _signin(client, cast.admin)
    body = await _ranking(client)
    row = _row(body, "OBSOLETE_FORM")

    assert (row["count"], row["prior_count"], row["trend"]) == (0, 1, insights.DOWN)
    assert body["items"][-1]["code"] == "OBSOLETE_FORM"
    # It is not a return "in the window" — the header counts the period, the row
    # explains the period before it, and the two must not be conflated.
    assert body["total_returns"] == 0


# --- "aggregates only": scope IS the privacy boundary (spec §11, §14.7) -----


async def test_a_plain_traveller_is_refused_not_shown_an_empty_ranking(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """api-standards §9f/§9h. ``staff`` holds ``reimb.claim.read`` GLOBALLY so a
    traveller can read their own claim — a ranking keyed on the route's
    permission would hand every employee the agency's failure profile.

    403, not ``200`` with an empty list: an empty ranking asserts "nothing comes
    back for any reason", which is false. The refusal names what this actor CAN
    see — their own returns, with reasons, on the claim tracker — rather than
    borrowing the queue's "your claims are on My Work", which is the wrong
    remedy for this question.
    """
    cast = await _returned(app_session, make_user)
    await app_session.commit()

    await _signin(client, cast.owner)
    refused = await client.get(RANKING)

    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "reimb_insights_not_permitted"


async def test_a_scoped_overseer_never_counts_a_sibling_office(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """The aggregate spans exactly the claims this actor could already open one
    at a time — which is what makes "no per-person counts" enforceable rather
    than aspirational, and why no minimum-cell suppression is applied."""
    mine = await _returned(app_session, make_user, "UNSIGNED")
    theirs = await _returned(app_session, make_user, "UNSIGNED")
    await _extra_returned(app_session, theirs, "UNSIGNED")
    assert mine.office.id != theirs.office.id
    await app_session.commit()

    await _signin(client, mine.admin)
    body = await _ranking(client)

    assert _row(body, "UNSIGNED")["count"] == 1
    assert body["total_returns"] == 1


async def test_a_global_grant_spans_every_office(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """Membership only, never a count — a global ranking spans the shared test
    database, so any number here would be about every other test in the suite."""
    one = await _returned(app_session, make_user, "PER_DIEM_CALC")
    two = await _returned(app_session, make_user, "PER_DIEM_CALC")
    boss, _ = await make_user()
    await grant_scoped_role(
        app_session, user=boss, role_code="admin_officer", org_unit_id=None
    )
    assert one.office.id != two.office.id
    await app_session.commit()

    await _signin(client, boss)
    body = await _ranking(client)

    assert _row(body, "PER_DIEM_CALC")["count"] >= 2


async def test_a_return_on_a_later_cancelled_claim_still_counts(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """The recorded R-8 decision, pinned so it is a choice and not an accident.

    Spec §6.1 row 9 excludes cancelled claims from KPIs, and the pipeline board
    honours that — a voided claim moved no money. This is not a KPI: the fact
    being counted is the RETURN EVENT, not the claim's outcome. A packet that
    came back for a missing OR came back for a missing OR, and cancelling it
    afterwards does not unlearn the lesson.
    """
    cast = await _returned(app_session, make_user, "MISSING_OR")
    await claim_action(
        app_session,
        claim_id=cast.claim.id,
        action="cancel",
        actor_user_id=cast.owner.id,
        comment="Trip did not happen.",
    )
    assert cast.claim.status == st.CANCELLED
    await app_session.commit()

    await _signin(client, cast.admin)
    body = await _ranking(client)

    assert _row(body, "MISSING_OR")["count"] == 1


# --- promotion: the loop's payoff, and the deploy that must not happen ------


async def test_promoting_shows_the_reason_to_the_wizard_with_no_deploy(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """Spec §14's R-8 sentence, end to end, in one test.

    The Admin Officer POSTs once; the taxonomy the WIZARD reads
    (``GET /return-reasons``, the same list the return dialog uses) starts
    saying ``promoted: true``; the demote turns it off again. Nothing is
    deployed, restarted or migrated in between — the entire wire is one boolean
    on a lookup row, which is what rule 10 buys.
    """
    cast = await _returned(app_session, make_user, "MISSING_OR")
    boss, _ = await make_user()
    await grant_scoped_role(
        app_session, user=boss, role_code="admin_officer", org_unit_id=None
    )
    await app_session.commit()
    reason_id = (await return_reason_ids(app_session, "MISSING_OR"))[0]

    await _signin(client, boss)
    try:
        before = await client.get(f"{BASE}/return-reasons")
        assert before.status_code == 200
        assert not _row({"items": before.json()}, "MISSING_OR")["promoted"]

        promoted = await client.post(
            f"{RANKING}/{reason_id}/promote", headers=CSRF
        )
        assert promoted.status_code == 200, promoted.text
        assert _row(promoted.json(), "MISSING_OR")["promoted"] is True

        during = await client.get(f"{BASE}/return-reasons")
        assert _row({"items": during.json()}, "MISSING_OR")["promoted"] is True

        demoted = await client.post(f"{RANKING}/{reason_id}/demote", headers=CSRF)
        assert demoted.status_code == 200, demoted.text
        assert _row(demoted.json(), "MISSING_OR")["promoted"] is False

        after = await client.get(f"{BASE}/return-reasons")
        assert _row({"items": after.json()}, "MISSING_OR")["promoted"] is False
    finally:
        # Belt: the assertions above end demoted, but a failure mid-test must
        # not leave a tenant-wide warning standing for the rest of the suite.
        row = (
            await app_session.execute(
                select(ReimbReturnReasonCatalog).where(
                    ReimbReturnReasonCatalog.id == reason_id
                )
            )
        ).scalar_one()
        if row.promoted_check:
            row.promoted_check = False
            await app_session.commit()
    assert cast.claim.status == st.RETURNED


async def test_the_ranking_says_which_reasons_are_already_promoted(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """A promote button that cannot tell you it has already been pressed is how
    the same reason gets promoted three times and demoted once."""
    cast = await _returned(app_session, make_user, "MISSING_OR", "UNSIGNED")
    await app_session.commit()

    await _signin(client, cast.admin)
    async with _promoted(app_session, "MISSING_OR"):
        body = await _ranking(client)
        assert _row(body, "MISSING_OR")["promoted"] is True
        assert _row(body, "UNSIGNED")["promoted"] is False

    assert _row(await _ranking(client), "MISSING_OR")["promoted"] is False


async def test_a_scoped_admin_officer_may_read_but_not_promote(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """The one place in this module where the write rule is NARROWER than the
    read rule, and the reason is scope: a promotion shows a warning to every
    claimant in the agency, so a grant covering one office cannot make it.

    ``can_promote`` rides the envelope so the button is never offered to someone
    certain to be refused (the R-4-screens doctrine), and the refusal names the
    missing grant rather than being mysterious.
    """
    cast = await _returned(app_session, make_user)
    await app_session.commit()
    reason_id = (await return_reason_ids(app_session, "MISSING_OR"))[0]

    await _signin(client, cast.admin)
    body = await _ranking(client)
    assert body["can_promote"] is False

    refused = await client.post(f"{RANKING}/{reason_id}/promote", headers=CSRF)
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "reimb_promotion_not_permitted"

    row = (
        await app_session.execute(
            select(ReimbReturnReasonCatalog).where(
                ReimbReturnReasonCatalog.id == reason_id
            )
        )
    ).scalar_one()
    await app_session.refresh(row)
    assert row.promoted_check is False


async def test_a_retired_reason_cannot_become_a_warning(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """When in doubt, do not warn. Warning claimants about a rule nobody
    enforces any more spends the credibility of every warning beside it."""
    await _returned(app_session, make_user, "OBSOLETE_FORM")
    boss, _ = await make_user()
    await grant_scoped_role(
        app_session, user=boss, role_code="admin_officer", org_unit_id=None
    )
    row = (
        await app_session.execute(
            select(ReimbReturnReasonCatalog).where(
                ReimbReturnReasonCatalog.code == "OBSOLETE_FORM"
            )
        )
    ).scalar_one()
    row.is_active = False
    await app_session.commit()

    await _signin(client, boss)
    try:
        refused = await client.post(f"{RANKING}/{row.id}/promote", headers=CSRF)
        assert refused.status_code == 422
        assert refused.json()["error"]["code"] == "reimb_reason_not_promotable"

        # It still RANKS — a retired reason explains the returns it caused, and
        # a ranking that hid them would under-report its own history. It simply
        # cannot be promoted, and the row says so.
        body = await _ranking(client)
        assert _row(body, "OBSOLETE_FORM")["promotable"] is False
    finally:
        row.is_active = True
        await app_session.commit()


async def test_a_promotion_is_written_to_the_audit_chain(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """Standing rule 5. Promoting is an admin act on a tenant-wide catalog whose
    effect every claimant sees, so ``who and when`` must be answerable — which
    is also why no promotion table was needed. It is written load-and-mutate,
    never as a bulk UPDATE, because ``core/audit.py`` refuses those (the
    R-7-events lesson)."""
    await _returned(app_session, make_user)
    boss, _ = await make_user()
    await grant_scoped_role(
        app_session, user=boss, role_code="admin_officer", org_unit_id=None
    )
    await app_session.commit()
    reason_id = (await return_reason_ids(app_session, "UNSIGNED"))[0]

    await _signin(client, boss)
    try:
        assert (
            await client.post(f"{RANKING}/{reason_id}/promote", headers=CSRF)
        ).status_code == 200

        rows = (
            (
                await app_session.execute(
                    select(AuditLog)
                    .where(
                        AuditLog.table_name == "reimb_return_reason_catalogs",
                        AuditLog.row_pk == reason_id,
                        AuditLog.action == "update",
                    )
                    .order_by(AuditLog.id.desc())
                )
            )
            .scalars()
            .all()
        )
        assert rows, "the promotion left no audit row"
        assert rows[0].actor_id == boss.id
        assert rows[0].new_data["promoted_check"] is True
    finally:
        await client.post(f"{RANKING}/{reason_id}/demote", headers=CSRF)


# --- api-standards §9g: a view is a sibling path ---------------------------


async def test_insights_is_a_sibling_segment_not_a_claim(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """R-7-board's lesson, pinned a second time so it outlives the decision.

    ``claims.router`` is included first and declares ``GET /claims/{claim_id}``
    with no convertor, so a literal segment beneath it is read as a claim whose
    id is that word. BOTH halves are asserted — the path that works, and the
    tempting one that cannot — because the reason is invisible in the code.
    """
    cast = await _returned(app_session, make_user)
    await app_session.commit()

    await _signin(client, cast.admin)
    assert (await client.get(RANKING)).status_code == 200
    assert (await client.get(f"{BASE}/claims/insights")).status_code == 422
