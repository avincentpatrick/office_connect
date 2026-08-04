"""R-6-liq-settle QA gate: settling a liquidation and claiming the difference.

R-6-liq-chain walked a liquidation to ``settled`` with no money recorded at all.
This is the money: spec §6.2's two side-steps (a refund evidenced by a DOH
official receipt, a "Reimbursement Due" spawn for an over-advance), the
exact-match case that needs neither, and the guard that stops ``settled`` being
asserted before the advance is actually closed.

The fixture trip costs ₱6,500, so the advance decides the branch:
₱6,000 → over-advance (₱500 due the traveller) · ₱8,000 → refund (₱1,500 back)
₱6,500 → exact.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from office_connect.core.api.errors import APIError
from office_connect.core.models.notification import NotificationOutbox
from office_connect.modules.reimbursement.models import (
    ReimbClaim,
    ReimbItineraryLeg,
)
from office_connect.modules.reimbursement.seeds import apply_reimbursement_seeds
from office_connect.modules.reimbursement.services import cash_advance as ca
from office_connect.modules.reimbursement.services import liquidation as liq
from office_connect.modules.reimbursement.services import settlement
from office_connect.modules.reimbursement.services import status as st
from office_connect.modules.reimbursement.services.actions import SETTLE, claim_actions
from office_connect.modules.reimbursement.services.lifecycle import (
    claim_action,
    submit_claim,
)
from tests.reimb_checklist_helpers import satisfy_packet
from tests.reimb_lifecycle_helpers import (
    ensure_reimb_workflow,
    standard_cast,
)
from tests.reimbursement_helpers import make_leg

UTC = timezone.utc
NOW = datetime(2026, 7, 6, 2, 0, tzinfo=UTC)  # Mon 2026-07-06 10:00 Manila
RETURN = date(2026, 7, 3)
JUL1 = date(2026, 7, 1)
OR_DATE = date(2026, 7, 9)


async def _handed_to_fms(app_session, make_user, *, advance_amount: str):
    """A liquidation walked all the way to ``handed_to_fms`` — one rung short of
    the money. ``advance_amount`` against the ₱6,500 fixture trip is what picks
    which of spec §6.2's branches the settlement will take."""
    cast = await standard_cast(app_session, make_user)
    await apply_reimbursement_seeds(app_session)
    await ensure_reimb_workflow(app_session)
    cast.advance = await ca.create_cash_advance(
        app_session,
        claimant_id=cast.staff.id,
        amount=Decimal(advance_amount),
        actor_user_id=cast.admin.id,
        dv_no="DV-2026-0007",
        dv_date=date(2026, 6, 25),
        dpo_no="DPO-2026-0042",
        date_return=RETURN,
        now=NOW,
    )
    claim = await liq.start_liquidation(
        app_session,
        cash_advance_id=cast.advance.id,
        actor_user_id=cast.owner.id,
        now=NOW,
    )
    claim.date_depart = JUL1
    claim.destination_region_code = "13"
    await make_leg(
        app_session, claim_id=claim.id, seq=1, leg_date=JUL1,
        destination_region_code="13", transport_mode="bus", fare="500.00",
    )
    await make_leg(
        app_session, claim_id=claim.id, seq=2, leg_date=RETURN,
        transport_mode="bus", fare="500.00",
    )
    await satisfy_packet(app_session, claim=claim, actor_user_id=cast.owner.id)
    await app_session.flush()

    await submit_claim(
        app_session, claim_id=claim.id, actor_user_id=cast.owner.id, now=NOW
    )
    await claim_action(
        app_session, claim_id=claim.id, action="approve",
        actor_user_id=cast.approver.id, now=NOW,
    )
    await claim_action(
        app_session, claim_id=claim.id, action="approve",
        actor_user_id=cast.admin.id, comment="Wet signature recorded.", now=NOW,
    )
    assert claim.status == st.HANDED_TO_FMS
    cast.claim = claim
    return cast


# --- the three branches ----------------------------------------------------


async def test_a_refund_records_the_official_receipt(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    """₱8,000 advanced against a ₱6,500 trip: ₱1,500 comes back, and the OR is
    the only proof it did — the line a COA auditor traces from the Liquidation
    Report into the books."""
    cast = await _handed_to_fms(app_session, make_user, advance_amount="8000.00")
    assert cast.claim.totals["to_refund"] == "1500.00"

    await settlement.record_settlement(
        app_session,
        claim_id=cast.claim.id,
        actor_user_id=cast.admin.id,
        or_no="OR-2026-1234",
        or_date=OR_DATE,
        now=NOW,
    )

    assert cast.claim.status == st.SETTLED
    assert cast.advance.status == ca.SETTLED
    assert cast.advance.settlement_mode == ca.REFUND
    assert cast.advance.refund_or_no == "OR-2026-1234"
    assert cast.advance.refund_or_date == OR_DATE
    assert cast.advance.refund_amount == Decimal("1500.00")
    assert cast.advance.settled_at == NOW
    assert cast.advance.settled_by == cast.admin.id
    await app_session.rollback()


async def test_an_over_advance_settles_with_no_receipt(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    """₱6,000 against ₱6,500: nothing came back, so there is no receipt to
    record and the refund columns stay null."""
    cast = await _handed_to_fms(app_session, make_user, advance_amount="6000.00")
    assert cast.claim.totals["to_reimburse"] == "500.00"

    await settlement.record_settlement(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.admin.id, now=NOW
    )

    assert cast.claim.status == st.SETTLED
    assert cast.advance.settlement_mode == ca.OVER_ADVANCE
    assert cast.advance.refund_or_no is None
    assert cast.advance.refund_amount is None
    await app_session.rollback()


async def test_an_exact_match_settles_with_neither_side_step(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    """The case spec §6.2 does not name, because it needs no side-step."""
    cast = await _handed_to_fms(app_session, make_user, advance_amount="6500.00")
    assert cast.claim.totals["to_refund"] == "0.00"
    assert cast.claim.totals["to_reimburse"] == "0.00"

    await settlement.record_settlement(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.admin.id, now=NOW
    )

    assert cast.claim.status == st.SETTLED
    assert cast.advance.settlement_mode == ca.EXACT
    await app_session.rollback()


# --- the receipt rules -----------------------------------------------------


async def test_a_refund_without_its_receipt_is_refused(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    cast = await _handed_to_fms(app_session, make_user, advance_amount="8000.00")
    with pytest.raises(APIError) as ei:
        await settlement.record_settlement(
            app_session, claim_id=cast.claim.id, actor_user_id=cast.admin.id,
            now=NOW,
        )
    assert ei.value.code == "reimb_refund_receipt_required"
    assert "1500.00" in ei.value.message
    # Nothing was written — the refusals all fire before any mutation.
    assert cast.advance.status != ca.SETTLED
    assert cast.claim.status == st.HANDED_TO_FMS
    await app_session.rollback()


async def test_a_receipt_where_nothing_was_refunded_is_refused(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    """An OR on a settlement that refunded nothing is a receipt for a payment
    that never happened."""
    cast = await _handed_to_fms(app_session, make_user, advance_amount="6000.00")
    with pytest.raises(APIError) as ei:
        await settlement.record_settlement(
            app_session, claim_id=cast.claim.id, actor_user_id=cast.admin.id,
            or_no="OR-2026-9999", or_date=OR_DATE, now=NOW,
        )
    assert ei.value.code == "reimb_refund_receipt_not_applicable"
    await app_session.rollback()


async def test_an_echoed_amount_that_disagrees_is_refused(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    """The client may ECHO the server's figure so a stale screen is caught. It
    may never propose one — money is server-computed (standing prohibition)."""
    cast = await _handed_to_fms(app_session, make_user, advance_amount="8000.00")
    with pytest.raises(APIError) as ei:
        await settlement.record_settlement(
            app_session, claim_id=cast.claim.id, actor_user_id=cast.admin.id,
            or_no="OR-2026-1234", or_date=OR_DATE,
            refund_amount=Decimal("1200.00"), now=NOW,
        )
    assert ei.value.code == "reimb_refund_amount_mismatch"
    assert "1500.00" in ei.value.message
    await app_session.rollback()


# --- the chokepoint --------------------------------------------------------


async def test_a_bare_approve_cannot_close_a_liquidation(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    """``settled`` ASSERTS the advance is closed. The engine's approve carries
    no payload, so it may not be the thing that asserts it."""
    cast = await _handed_to_fms(app_session, make_user, advance_amount="6000.00")
    with pytest.raises(APIError) as ei:
        await claim_action(
            app_session, claim_id=cast.claim.id, action="approve",
            actor_user_id=cast.admin.id, now=NOW,
        )
    assert ei.value.code == "reimb_settlement_required"
    assert ei.value.details == [{"claim_id": cast.claim.id, "action": "settle"}]
    await app_session.rollback()


async def test_the_offered_verb_is_settle_not_approve(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    """Never offer a button certain to fail — but the actor IS authorized here,
    so the verb is REWRITTEN rather than dropped. A hole would leave the
    approver with no button at the one gate they must clear."""
    cast = await _handed_to_fms(app_session, make_user, advance_amount="6000.00")
    verbs = await claim_actions(
        app_session, claim=cast.claim, actor_user_id=cast.admin.id
    )
    assert SETTLE in verbs
    assert "approve" not in verbs
    # The remedy for a liquidation FMS bounces back is untouched.
    assert "return" in verbs
    await app_session.rollback()


async def test_settling_twice_says_repeat_not_race(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    """The engine's own answer would be ``workflow_state_conflict`` ("someone
    finished it first"), which is a sentence about a race. This is a repeat."""
    cast = await _handed_to_fms(app_session, make_user, advance_amount="6000.00")
    await settlement.record_settlement(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.admin.id, now=NOW
    )
    with pytest.raises(APIError) as ei:
        await settlement.record_settlement(
            app_session, claim_id=cast.claim.id, actor_user_id=cast.admin.id,
            now=NOW,
        )
    assert ei.value.code == "reimb_settlement_already_recorded"
    await app_session.rollback()


async def test_settlement_refuses_before_fms_has_it(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    cast = await standard_cast(app_session, make_user)
    await apply_reimbursement_seeds(app_session)
    await ensure_reimb_workflow(app_session)
    advance = await ca.create_cash_advance(
        app_session, claimant_id=cast.staff.id, amount=Decimal("6000.00"),
        actor_user_id=cast.admin.id, date_return=RETURN, now=NOW,
    )
    claim = await liq.start_liquidation(
        app_session, cash_advance_id=advance.id, actor_user_id=cast.owner.id,
        now=NOW,
    )
    with pytest.raises(APIError) as ei:
        await settlement.record_settlement(
            app_session, claim_id=claim.id, actor_user_id=cast.admin.id, now=NOW
        )
    assert ei.value.code == "reimb_settlement_wrong_state"
    await app_session.rollback()


async def test_a_reimbursement_claim_is_paid_not_settled(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    cast = await standard_cast(app_session, make_user)
    with pytest.raises(APIError) as ei:
        await settlement.record_settlement(
            app_session, claim_id=cast.claim.id, actor_user_id=cast.admin.id,
            now=NOW,
        )
    assert ei.value.code == "reimb_not_a_liquidation"
    await app_session.rollback()


# --- the §89 slot + the overdue path ---------------------------------------


async def test_settling_releases_the_section_89_slot(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    """PD 1445 §89 allows one unliquidated advance at a time. Before this
    increment NOTHING ever released the slot, so a traveller who liquidated
    correctly could still never be advanced again."""
    cast = await _handed_to_fms(app_session, make_user, advance_amount="6000.00")
    with pytest.raises(APIError) as ei:
        await ca.create_cash_advance(
            app_session, claimant_id=cast.staff.id, amount=Decimal("1000.00"),
            actor_user_id=cast.admin.id, date_return=RETURN, now=NOW,
        )
    assert ei.value.code == "reimb_cash_advance_unliquidated"

    await settlement.record_settlement(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.admin.id, now=NOW
    )
    second = await ca.create_cash_advance(
        app_session, claimant_id=cast.staff.id, amount=Decimal("1000.00"),
        actor_user_id=cast.admin.id, date_return=date(2026, 9, 1), now=NOW,
    )
    assert second.status == ca.OPEN
    await app_session.rollback()


async def test_an_overdue_advance_can_still_be_settled(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    """``mark_overdue``'s guard is an allow-list of (open, liquidation_started).
    Copied into ``mark_settled`` it would make an overdue advance unsettleable —
    and overdue advances are exactly the ones Accounting needs to close."""
    cast = await _handed_to_fms(app_session, make_user, advance_amount="6000.00")
    assert await ca.mark_overdue(
        app_session, cash_advance=cast.advance, actor_user_id=cast.admin.id
    )
    assert cast.advance.status == ca.OVERDUE

    await settlement.record_settlement(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.admin.id, now=NOW
    )
    assert cast.advance.status == ca.SETTLED
    await app_session.rollback()


async def test_a_settled_advance_stops_counting_down(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    """A closed advance is not counting down to anything. Left alone, a
    settled-but-late record would render a red Overdue ring and the COA
    consequence copy forever — threatening a traveller who already answered."""
    from office_connect.modules.reimbursement.api.deps import cash_advance_out

    cast = await _handed_to_fms(app_session, make_user, advance_amount="6000.00")
    await settlement.record_settlement(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.admin.id, now=NOW
    )
    out = await cash_advance_out(
        app_session,
        cast.advance,
        today=date(2026, 9, 30),  # long past the 2026-08-02 deadline
        overdue_note="COA says …",
    )
    assert out.deadline_state is None
    assert out.days_remaining is None
    assert out.overdue_note is None
    assert out.settlement_mode == ca.OVER_ADVANCE
    await app_session.rollback()


# --- the "Reimbursement Due" spawn -----------------------------------------


async def _settled_over_advance(app_session, make_user):
    cast = await _handed_to_fms(app_session, make_user, advance_amount="6000.00")
    await settlement.record_settlement(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.admin.id, now=NOW
    )
    return cast


async def test_the_spawn_nets_the_advance_to_the_difference(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    """Spec §6.2's "one tap, pre-filled". The spawn carries the SAME trip and
    points at the SAME advance, so its DV prints the standard GAM shape —
    Total claim / Less: cash advance / Amount due the payee — and the payee line
    is the difference, not a fabricated "other expense"."""
    cast = await _settled_over_advance(app_session, make_user)
    spawn = await settlement.spawn_reimbursement(
        app_session, liquidation_claim_id=cast.claim.id,
        actor_user_id=cast.owner.id, now=NOW,
    )

    assert spawn.kind == st.REIMBURSEMENT_KIND
    assert spawn.status == st.DRAFT
    assert spawn.spawned_from_claim_id == cast.claim.id
    assert spawn.cash_advance_id == cast.advance.id
    # The trip carried over verbatim — nothing the traveller must retype.
    assert spawn.purpose == cast.claim.purpose
    assert spawn.date_depart == cast.claim.date_depart
    assert spawn.date_return == cast.claim.date_return
    assert spawn.dpo_no == cast.claim.dpo_no
    legs = (
        (
            await app_session.execute(
                select(ReimbItineraryLeg)
                .where(ReimbItineraryLeg.claim_id == spawn.id)
                .order_by(ReimbItineraryLeg.seq)
            )
        ).scalars().all()
    )
    assert [leg.seq for leg in legs] == [1, 2]
    # The money: same trip, less the advance.
    assert spawn.totals["grand"] == "6500.00"
    assert spawn.totals["advance"] == "6000.00"
    assert spawn.totals["to_reimburse"] == "500.00"
    assert spawn.totals["to_refund"] == "0.00"
    # And NO countdown: a reimbursement answers no liquidation clock.
    assert spawn.liquidation_deadline is None
    await app_session.rollback()


async def test_only_the_traveller_may_claim_the_difference(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    """Recording the settlement is the Admin Officer's act; claiming what you
    are owed is yours. `create_draft_claim` mints for the ACTOR, so an admin
    tapping this would have made a claim in their own name."""
    cast = await _settled_over_advance(app_session, make_user)
    with pytest.raises(APIError) as ei:
        await settlement.spawn_reimbursement(
            app_session, liquidation_claim_id=cast.claim.id,
            actor_user_id=cast.admin.id, now=NOW,
        )
    assert ei.value.code == "reimb_not_advance_holder"
    await app_session.rollback()


async def test_only_an_over_advance_spawns(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    cast = await _handed_to_fms(app_session, make_user, advance_amount="8000.00")
    await settlement.record_settlement(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.admin.id,
        or_no="OR-2026-1234", or_date=OR_DATE, now=NOW,
    )
    with pytest.raises(APIError) as ei:
        await settlement.spawn_reimbursement(
            app_session, liquidation_claim_id=cast.claim.id,
            actor_user_id=cast.owner.id, now=NOW,
        )
    assert ei.value.code == "reimb_spawn_not_over_advance"
    await app_session.rollback()


async def test_one_live_spawn_per_liquidation(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    cast = await _settled_over_advance(app_session, make_user)
    first = await settlement.spawn_reimbursement(
        app_session, liquidation_claim_id=cast.claim.id,
        actor_user_id=cast.owner.id, now=NOW,
    )
    with pytest.raises(APIError) as ei:
        await settlement.spawn_reimbursement(
            app_session, liquidation_claim_id=cast.claim.id,
            actor_user_id=cast.owner.id, now=NOW,
        )
    assert ei.value.code == "reimb_spawn_exists"
    assert ei.value.details == [{"claim_id": first.id, "ref_no": first.ref_no}]
    await app_session.rollback()


async def test_a_spawn_edited_below_its_advance_cannot_submit(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    """`settle` would return a REFUND on a reimbursement claim, and DV-32 would
    print "Amount refundable" — a liquidation's sentence, on a payment
    instrument."""
    from office_connect.modules.reimbursement.services.drafts import replace_legs

    cast = await _settled_over_advance(app_session, make_user)
    spawn = await settlement.spawn_reimbursement(
        app_session, liquidation_claim_id=cast.claim.id,
        actor_user_id=cast.owner.id, now=NOW,
    )
    # Drop the two ₱500 fares: grand falls to ₱5,500 against a ₱6,000 advance,
    # so `settle` flips to a refund. (The legs stay — an empty itinerary fails
    # earlier, on `reimb_no_computable_days`, which is a different guard.)
    await replace_legs(
        app_session,
        claim_id=spawn.id,
        actor_user_id=cast.owner.id,
        legs=[
            {
                "leg_date": JUL1,
                "destination_region_code": "13",
                "transport_mode": "bus",
            },
            {"leg_date": RETURN, "transport_mode": "bus"},
        ],
    )
    await satisfy_packet(app_session, claim=spawn, actor_user_id=cast.owner.id)
    with pytest.raises(APIError) as ei:
        await submit_claim(
            app_session, claim_id=spawn.id, actor_user_id=cast.owner.id, now=NOW
        )
    assert ei.value.code == "reimb_spawn_below_advance"
    await app_session.rollback()


# --- the loop that would otherwise never close -----------------------------


async def test_an_over_advance_settlement_tells_the_traveller(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    """Settlement is the Admin Officer's act and the spawn is the traveller's.
    Without this nudge nobody is ever told they are owed money, and spec §6.2's
    "one tap" is a tap nobody knows to make."""
    cast = await _settled_over_advance(app_session, make_user)
    rows = (
        (
            await app_session.execute(
                select(NotificationOutbox).where(
                    NotificationOutbox.meta["kind"].astext
                    == "liquidation_settled",
                    # Scoped to THIS advance: the outbox is shared and the suite
                    # persists rows across files.
                    NotificationOutbox.meta["cash_advance_id"].astext
                    == str(cast.advance.id),
                )
            )
        ).scalars().all()
    )
    assert len(rows) == 1
    assert rows[0].meta["recipient_user_id"] == cast.owner.id
    assert rows[0].meta["settlement_mode"] == ca.OVER_ADVANCE
    assert "₱500.00" in rows[0].meta["subject"]
    await app_session.rollback()


# --- the two halves point at each other ------------------------------------


async def test_the_two_halves_point_at_each_other(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    from office_connect.modules.reimbursement.api.deps import claim_detail

    cast = await _settled_over_advance(app_session, make_user)
    spawn = await settlement.spawn_reimbursement(
        app_session, liquidation_claim_id=cast.claim.id,
        actor_user_id=cast.owner.id, now=NOW,
    )
    liquidation_detail = await claim_detail(
        app_session, cast.claim, actor_user_id=cast.owner.id
    )
    assert liquidation_detail.spawned_claim.claim_id == spawn.id
    assert liquidation_detail.spawned_from is None

    spawn_detail = await claim_detail(
        app_session, spawn, actor_user_id=cast.owner.id
    )
    assert spawn_detail.spawned_from.claim_id == cast.claim.id
    assert spawn_detail.spawned_claim is None
    await app_session.rollback()


async def test_a_cancelled_spawn_can_be_re_taken(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    """`cancelled` is out of the live set for the same reason it is out of
    `liquidation.LIVE_STATUSES`: a mistaken tap must not strand the money."""
    from office_connect.modules.reimbursement.services.lifecycle import (
        cancel_draft_claim,
    )

    cast = await _settled_over_advance(app_session, make_user)
    first = await settlement.spawn_reimbursement(
        app_session, liquidation_claim_id=cast.claim.id,
        actor_user_id=cast.owner.id, now=NOW,
    )
    await cancel_draft_claim(
        app_session, claim_id=first.id, actor_user_id=cast.owner.id,
        comment="Filed by mistake.",
    )
    second = await settlement.spawn_reimbursement(
        app_session, liquidation_claim_id=cast.claim.id,
        actor_user_id=cast.owner.id, now=NOW,
    )
    assert second.id != first.id
    assert second.spawned_from_claim_id == cast.claim.id
    await app_session.rollback()


# --- the deferred 0020 belt ------------------------------------------------


async def test_the_belt_catches_a_liquidation_the_service_check_cannot_see(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    """Migration 0020's index predicate is WIDER than `LIVE_STATUSES`: it uses
    `status IS DISTINCT FROM 'cancelled'`, which includes an un-stamped NULL
    status, while the service check uses `IN (live states)`, which does not.
    A row in that gap must produce the named 409, never a raw IntegrityError."""
    from tests.reimbursement_helpers import make_claim

    cast = await standard_cast(app_session, make_user)
    await apply_reimbursement_seeds(app_session)
    await ensure_reimb_workflow(app_session)
    advance = await ca.create_cash_advance(
        app_session, claimant_id=cast.staff.id, amount=Decimal("6000.00"),
        actor_user_id=cast.admin.id, date_return=RETURN, now=NOW,
    )
    # A NULL-status liquidation: invisible to `liquidation_for_advance`, caught
    # by the index.
    await make_claim(
        app_session, claimant_id=cast.staff.id, kind="liquidation",
        cash_advance_id=advance.id,
    )
    with pytest.raises(APIError) as ei:
        await liq.start_liquidation(
            app_session, cash_advance_id=advance.id,
            actor_user_id=cast.owner.id, now=NOW,
        )
    assert ei.value.code == "reimb_liquidation_exists"
    await app_session.rollback()
