"""R-7-events — the FMS status relay (``reimb_external_events``'s first writer).

Two things are on trial, and the first is the one that would be easiest to get
wrong by being helpful.

**Order is NOT a rule.** Spec §6.1 row 6 reads *With Budget → With Accounting →
Payment Processing (admin, **any order/skips allowed**)*, and the R-9 QA line is
literally "Statuses skip/reorder legally". The arrow in the spec is a typical
journey, not a sequence to enforce — FMS routinely pays straight out of Budget,
sends a packet back to a desk it already left, and tells you twice in a week
that it is still with Accounting. Every one of those is a legal relay here, and
the tests below are what stop a future "tidy-up" from adding the state machine
the design deliberately does not have.

**The relay moves nothing.** The sub-statuses are not workflow states (delta row
38): they ride the event table over the single ``handed_to_fms`` state. So after
three relays the claim's status, holder, ``holder_since`` and transition history
must be byte-for-byte what they were before — which is also what keeps R-7-queue's
">10 working days with FMS" clock honest, since that clock counts from
``holder_since`` and a relay is news, not progress.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from office_connect.core.api.errors import APIError
from office_connect.core.models.notification import NotificationOutbox
from office_connect.modules.reimbursement.models import (
    ReimbExternalEvent,
    ReimbStatusHistory,
)
from office_connect.modules.reimbursement.services import external
from office_connect.modules.reimbursement.services import status as st
from office_connect.modules.reimbursement.services.actions import (
    RELAY,
    claim_actions,
)
from office_connect.modules.reimbursement.services.lifecycle import (
    claim_action,
    submit_claim,
)
from tests.conftest import CSRF, DEFAULT_TEST_PASSWORD, login
from tests.reimb_lifecycle_helpers import return_reason_ids, standard_cast
from tests.workflow_helpers import grant_scoped_role, make_org_unit

BASE = "/api/v1/reimbursement"
UTC = timezone.utc
NOW = datetime(2026, 7, 6, 2, 0, tzinfo=UTC)  # Mon 2026-07-06 10:00 Manila
TODAY_MANILA = date(2026, 7, 6)


async def _at_fms(app_session, make_user, **cast_kw):
    """The standard cast, driven to ``handed_to_fms`` — the one state where FMS
    has the packet and this whole module has anything to say."""
    cast = await standard_cast(app_session, make_user, **cast_kw)
    await submit_claim(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.owner.id, now=NOW
    )
    await claim_action(
        app_session, claim_id=cast.claim.id, action="approve",
        actor_user_id=cast.approver.id, now=NOW,
    )
    await claim_action(
        app_session, claim_id=cast.claim.id, action="approve",
        actor_user_id=cast.admin.id, now=NOW,
    )
    assert cast.claim.status == st.HANDED_TO_FMS
    return cast


async def _relay(app_session, cast, status, **kw):
    return await external.record_external_event(
        app_session,
        claim_id=cast.claim.id,
        status=status,
        actor_user_id=cast.admin.id,
        now=NOW,
        **kw,
    )


async def _events(app_session, claim_id) -> list[str]:
    return [e.status for e in await external.claim_events(app_session, claim_id)]


# --- order is not a rule ----------------------------------------------------


async def test_statuses_may_be_relayed_in_any_order_with_skips(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    """The spec sentence, executed. Accounting BEFORE Budget, and Payment
    Processing never mentioned — a packet FMS routed its own way."""
    cast = await _at_fms(app_session, make_user)

    await _relay(app_session, cast, external.WITH_ACCOUNTING)
    await _relay(app_session, cast, external.WITH_BUDGET)

    assert await _events(app_session, cast.claim.id) == [
        external.WITH_ACCOUNTING,
        external.WITH_BUDGET,
    ]
    await app_session.rollback()


async def test_a_repeat_is_legal_because_still_with_budget_is_a_real_answer(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    """An Admin Officer chasing a stalled packet gets the same answer twice, and
    recording it is the point: it is evidence the chase happened."""
    cast = await _at_fms(app_session, make_user)

    await _relay(app_session, cast, external.WITH_BUDGET)
    await _relay(app_session, cast, external.WITH_BUDGET, note="Chased again.")

    assert await _events(app_session, cast.claim.id) == [
        external.WITH_BUDGET,
        external.WITH_BUDGET,
    ]
    await app_session.rollback()


async def test_relaying_moves_nothing(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    """The delta-row-38 invariant, asserted rather than assumed.

    If a relay ever moved the claim it would also reset ``holder_since``, and
    R-7-queue's ">10 working days with FMS" filter — the one surface that makes
    a stalled packet visible — would silently restart its clock every time
    somebody phoned FMS. The bug would look like diligence.
    """
    cast = await _at_fms(app_session, make_user)
    before = (
        cast.claim.status,
        cast.claim.holder_kind,
        cast.claim.holder_id,
        cast.claim.holder_since,
        cast.claim.next_action,
    )
    history_before = (
        await app_session.execute(
            select(func.count())
            .select_from(ReimbStatusHistory)
            .where(ReimbStatusHistory.claim_id == cast.claim.id)
        )
    ).scalar_one()

    for status in external.RELAY_STATUSES:
        await _relay(app_session, cast, status)

    assert (
        cast.claim.status,
        cast.claim.holder_kind,
        cast.claim.holder_id,
        cast.claim.holder_since,
        cast.claim.next_action,
    ) == before
    history_after = (
        await app_session.execute(
            select(func.count())
            .select_from(ReimbStatusHistory)
            .where(ReimbStatusHistory.claim_id == cast.claim.id)
        )
    ).scalar_one()
    assert history_after == history_before
    await app_session.rollback()


# --- the closed set ---------------------------------------------------------


async def test_an_unknown_status_is_refused_and_the_message_says_order_is_free(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    """Membership is enforced; the refusal must not imply order is too.

    An operator who reads "use one of: with_budget, with_accounting,
    payment_processing" and infers a sequence will not relay Accounting on a
    packet that skipped Budget — so the sentence says so explicitly, and this
    pins that it does.
    """
    cast = await _at_fms(app_session, make_user)
    with pytest.raises(APIError) as ei:
        await _relay(app_session, cast, "with_the_cashier")
    assert ei.value.code == "reimb_unknown_external_status"
    assert "any order" in ei.value.message
    await app_session.rollback()


async def test_paid_cannot_be_relayed_because_it_closes_the_claim(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    """``paid`` is the terminal, not a sub-status. Typing it into the status
    dialog would close a claim with no payment reference — the exact hole
    R-7-events exists to fill — so it is refused, and the refusal names the
    route that does the thing."""
    cast = await _at_fms(app_session, make_user)
    with pytest.raises(APIError) as ei:
        await _relay(app_session, cast, external.PAID)
    assert ei.value.code == "reimb_external_status_is_terminal"
    assert ei.value.details == [{"action": "mark_paid"}]
    assert await _events(app_session, cast.claim.id) == []
    await app_session.rollback()


async def test_a_claim_the_bureau_still_holds_cannot_have_an_fms_status(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    """FMS cannot have a packet that never left the building."""
    cast = await standard_cast(app_session, make_user)
    await submit_claim(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.owner.id, now=NOW
    )
    with pytest.raises(APIError) as ei:
        await _relay(app_session, cast, external.WITH_BUDGET)
    assert ei.value.code == "reimb_external_event_wrong_state"
    assert "For Approval" in ei.value.message
    await app_session.rollback()


async def test_a_future_date_is_refused(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    """FMS cannot have done something tomorrow."""
    cast = await _at_fms(app_session, make_user)
    with pytest.raises(APIError) as ei:
        await _relay(
            app_session,
            cast,
            external.WITH_BUDGET,
            event_date=TODAY_MANILA + timedelta(days=1),
        )
    assert ei.value.code == "reimb_external_event_future_date"
    await app_session.rollback()


# --- a liquidation is with FMS too ------------------------------------------


async def test_a_liquidation_with_fms_can_be_relayed_the_same_way(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    """Delta row 116 excluded ``fms_returned`` from the liquidation chain — a
    STATE, needing a screen and a transition. A relay adds no state and reuses
    one dialog, and a liquidation sitting at ``handed_to_fms`` is exactly as
    invisible as a claim is. FMS runs both packets past the same three desks."""
    cast = await standard_cast(app_session, make_user, kind=st.LIQUIDATION_KIND)
    await submit_claim(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.owner.id, now=NOW
    )
    await claim_action(
        app_session, claim_id=cast.claim.id, action="approve",
        actor_user_id=cast.approver.id, now=NOW,
    )
    await claim_action(
        app_session, claim_id=cast.claim.id, action="approve",
        actor_user_id=cast.admin.id, comment="Certified.", now=NOW,
    )
    assert cast.claim.status == st.HANDED_TO_FMS

    await _relay(app_session, cast, external.WITH_ACCOUNTING)
    assert await _events(app_session, cast.claim.id) == [external.WITH_ACCOUNTING]
    await app_session.rollback()


# --- what the claimant hears (spec §12) -------------------------------------


async def _external_notices(app_session, claim_id) -> list[NotificationOutbox]:
    return list(
        (
            await app_session.execute(
                select(NotificationOutbox)
                .where(
                    NotificationOutbox.meta["kind"].astext == "external_status",
                    NotificationOutbox.meta["claim_id"].astext == str(claim_id),
                )
                .order_by(NotificationOutbox.id)
            )
        )
        .scalars()
        .all()
    )


async def test_the_claimant_is_told_when_the_status_actually_changes(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    """Spec §12: "External status updated → Claimant: 'Your claim is now With
    Accounting'". This is the one stretch of the journey where nothing in the
    platform moves, so silence reads as nothing happening."""
    cast = await _at_fms(app_session, make_user)
    await _relay(app_session, cast, external.WITH_ACCOUNTING)

    notices = await _external_notices(app_session, cast.claim.id)
    assert len(notices) == 1
    assert "With Accounting" in notices[0].meta["subject"]
    await app_session.rollback()


async def test_a_repeat_of_the_same_status_tells_the_claimant_nothing(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    """The notification's sentence is "your claim is NOW X" — a claim about
    change. Sending it again when nothing changed trains people to ignore it.
    The event is still recorded; only the nudge is withheld."""
    cast = await _at_fms(app_session, make_user)
    await _relay(app_session, cast, external.WITH_BUDGET)
    await _relay(app_session, cast, external.WITH_BUDGET)

    assert len(await _external_notices(app_session, cast.claim.id)) == 1
    assert len(await _events(app_session, cast.claim.id)) == 2
    await app_session.rollback()


async def test_re_entering_a_status_after_a_different_one_is_news_again(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    """Budget → Accounting → back to Budget. The third relay is a genuine
    change of where the packet is, so the claimant hears about it."""
    cast = await _at_fms(app_session, make_user)
    await _relay(app_session, cast, external.WITH_BUDGET)
    await _relay(app_session, cast, external.WITH_ACCOUNTING)
    await _relay(app_session, cast, external.WITH_BUDGET)

    assert len(await _external_notices(app_session, cast.claim.id)) == 3
    await app_session.rollback()


# --- who may relay ----------------------------------------------------------


async def test_the_action_set_offers_the_relay_only_to_an_fms_updater(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    """The R-4-screens doctrine: never offer a button certain to fail, and never
    let the browser decide who may act. The Admin Officer holds
    ``reimb.claim.fms_update``; the traveller and the division approver do not."""
    cast = await _at_fms(app_session, make_user)

    admin_verbs = await claim_actions(
        app_session, claim=cast.claim, actor_user_id=cast.admin.id
    )
    owner_verbs = await claim_actions(
        app_session, claim=cast.claim, actor_user_id=cast.owner.id
    )
    approver_verbs = await claim_actions(
        app_session, claim=cast.claim, actor_user_id=cast.approver.id
    )

    assert RELAY in admin_verbs
    assert RELAY not in owner_verbs
    assert RELAY not in approver_verbs
    await app_session.rollback()


async def test_the_relay_is_not_offered_once_the_packet_comes_back(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    """At ``fms_returned`` the packet is in the bureau's hands again — there is
    nothing left to relay, and the Admin Officer's job becomes passing FMS's
    comments to the claimant (spec §6.1 row 7)."""
    cast = await _at_fms(app_session, make_user)
    await claim_action(
        app_session, claim_id=cast.claim.id, action="return",
        actor_user_id=cast.admin.id, comment="FMS wants the OR reprinted.",
        reason_ids=await return_reason_ids(app_session), now=NOW,
    )
    assert cast.claim.status == st.FMS_RETURNED

    verbs = await claim_actions(
        app_session, claim=cast.claim, actor_user_id=cast.admin.id
    )
    assert RELAY not in verbs
    await app_session.rollback()


# --- over HTTP --------------------------------------------------------------


async def test_the_traveller_may_read_the_fms_journey_but_never_write_it(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """Reading your own claim and speaking for FMS about it are different acts.

    The refusal is deliberately NOT ``not_claim_owner`` — telling a traveller
    "only the claimant may do this" about their own claim would be nonsense —
    and it names whose job it actually is (§9.1 principle 4).
    """
    cast = await _at_fms(app_session, make_user)
    await external.record_external_event(
        app_session,
        claim_id=cast.claim.id,
        status=external.WITH_BUDGET,
        actor_user_id=cast.admin.id,
        noted_by="Ms. Reyes, Budget",
        now=NOW,
    )
    await app_session.commit()

    await login(client, cast.owner, DEFAULT_TEST_PASSWORD)
    listed = await client.get(f"{BASE}/claims/{cast.claim.id}/external-events")
    assert listed.status_code == 200
    assert [e["status_label"] for e in listed.json()] == ["With Budget"]

    refused = await client.post(
        f"{BASE}/claims/{cast.claim.id}/external-events",
        json={"status": external.WITH_ACCOUNTING},
        headers=CSRF,
    )
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "reimb_external_update_not_permitted"


async def test_the_relay_returns_the_whole_claim_with_the_latest_status_on_it(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """Every write on this surface answers with ``ClaimDetail``: the relay
    changes what the rail says and what the tracker shows, and a client that had
    to refetch to learn that would render a moment of disagreement."""
    cast = await _at_fms(app_session, make_user)
    await app_session.commit()

    await login(client, cast.admin, DEFAULT_TEST_PASSWORD)
    response = await client.post(
        f"{BASE}/claims/{cast.claim.id}/external-events",
        json={
            "status": external.PAYMENT_PROCESSING,
            "noted_by": "Mr. Cruz, Cashier",
            "note": "In the next ADA batch.",
        },
        headers=CSRF,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "handed_to_fms"  # unmoved
    assert body["latest_external"]["status_label"] == "Payment processing"
    assert body["latest_external"]["noted_by"] == "Mr. Cruz, Cashier"


async def test_the_queue_row_carries_the_last_thing_fms_said(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """R-7-queue answers "what is stuck"; the sub-status is what decides whether
    the follow-up call is worth making. A packet 12 days in Payment Processing
    is a different conversation from one 12 days in Budget."""
    cast = await _at_fms(app_session, make_user)
    boss, _ = await make_user()
    await grant_scoped_role(
        app_session, user=boss, role_code="admin_officer", org_unit_id=None
    )
    await external.record_external_event(
        app_session,
        claim_id=cast.claim.id,
        status=external.WITH_ACCOUNTING,
        actor_user_id=cast.admin.id,
        now=NOW,
    )
    await app_session.commit()

    await login(client, boss, DEFAULT_TEST_PASSWORD)
    # Filtered to this claimant: the suite shares a database and the queue is
    # ordered longest-waiting-first, so an unfiltered page 1 is other tests'
    # leftovers.
    listed = await client.get(f"{BASE}/claims?claimant_id={cast.staff.id}")
    row = next(
        item for item in listed.json()["items"] if item["id"] == cast.claim.id
    )
    assert row["external_status_label"] == "With Accounting"


# --- the table's own shape --------------------------------------------------


async def test_the_event_row_records_who_at_fms_said_it(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    """``noted_by`` is free text, not an FK: the person at FMS has no login
    here. It is a name an Admin Officer writes down, and it is the difference
    between a relay you can follow up and one you cannot."""
    cast = await _at_fms(app_session, make_user)
    event = await _relay(
        app_session,
        cast,
        external.WITH_BUDGET,
        noted_by="  Ms. Reyes, Budget  ",
        note="Endorsed to Accounting Friday.",
        event_date=date(2026, 7, 3),
    )

    row = await app_session.get(ReimbExternalEvent, event.id)
    assert row.noted_by == "Ms. Reyes, Budget"  # trimmed, not padded
    assert row.event_date == date(2026, 7, 3)
    assert row.created_by == cast.admin.id
    # Append-only class: created_* only, no updated_* to be had.
    assert not hasattr(row, "updated_at")
    await app_session.rollback()
