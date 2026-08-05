"""R-7-events — ``mark_paid``, the payout record, and the GRDS retention clock.

Spec §6.1 row 8 says ``Paid / Closed`` is "terminal (admin records payout ref)".
Until this increment it was a bare ``approve``: the claim went read-only holding
no reference, no date, and no way to add either. This file is the proof that it
cannot happen again, and it is workflow-standards §12's **second** instance —
the same three rules ``record_settlement`` established one chain over.

Three of these tests are the load-bearing ones:

- **The bare verb is refused.** ``POST /approve`` at ``handed_to_fms`` must 409
  and NAME ``mark-paid``, because a generic action route that can reach a state
  asserting facts it did not record is exactly the hole §12 rule 3 closes.
- **A stale CAS token writes NOTHING.** The reference is written before the
  transition (rule 2, so the token stays valid), which means a refused approve
  has to take the reference down with it. One transaction, or the claim keeps a
  payment reference for a payment it never recorded.
- **The retention clock starts.** ``services/attachments.py`` has been promising
  "R-7" since R-2, and until now ``retain_until()`` returned None for every
  claim attachment in the system.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from office_connect.core.api.errors import APIError
from office_connect.core.attachments import retention
from office_connect.core.models import Attachment
from office_connect.core.models.notification import NotificationOutbox
from office_connect.modules.reimbursement.seeds import apply_reimbursement_seeds
from office_connect.modules.reimbursement.services import cash_advance as ca
from office_connect.modules.reimbursement.services import external
from office_connect.modules.reimbursement.services import liquidation as liq
from office_connect.modules.reimbursement.services import settlement
from office_connect.modules.reimbursement.services import status as st
from office_connect.modules.reimbursement.services.actions import (
    MARK_PAID,
    SETTLE,
    claim_actions,
)
from office_connect.modules.reimbursement.services.lifecycle import (
    claim_action,
    submit_claim,
)
from tests.conftest import CSRF, DEFAULT_TEST_PASSWORD, login
from tests.reimb_checklist_helpers import satisfy_packet
from tests.reimb_lifecycle_helpers import ensure_reimb_workflow, standard_cast
from tests.reimbursement_helpers import make_leg
from tests.workflow_helpers import grant_scoped_role

BASE = "/api/v1/reimbursement"
UTC = timezone.utc
NOW = datetime(2026, 7, 6, 2, 0, tzinfo=UTC)  # Mon 2026-07-06 10:00 Manila
TODAY_MANILA = date(2026, 7, 6)
PAID_ON = date(2026, 7, 3)
ADA = "ADA-2026-00417"


async def _at_fms(app_session, make_user, **cast_kw):
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
        # The liquidation chain's certify_c→handed_to_fms is authored
        # `requires_comment=True` (the Accounting head signs on paper, and the
        # comment IS the record of that signature). Harmless on the claim chain.
        comment="Recorded.",
    )
    assert cast.claim.status == st.HANDED_TO_FMS
    return cast


async def _pay(app_session, cast, **kw):
    kw.setdefault("payout_ref", ADA)
    kw.setdefault("paid_on", PAID_ON)
    return await external.record_payout(
        app_session,
        claim_id=cast.claim.id,
        actor_user_id=cast.admin.id,
        now=NOW,
        **kw,
    )


# --- the happy path ---------------------------------------------------------


async def test_marking_paid_records_the_reference_and_closes_the_claim(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    """What spec §6.1 row 8 asked for, and what a bare approve never gave: the
    claim closes AND the record says what it closed on."""
    cast = await _at_fms(app_session, make_user)

    await _pay(app_session, cast, comment="ADA credited 3 July.")

    assert cast.claim.status == st.PAID_CLOSED
    assert cast.claim.payout_ref == ADA
    assert cast.claim.paid_on == PAID_ON
    assert cast.claim.paid_by == cast.admin.id
    # Terminal: nobody holds it any more (spec §6.1 shows "—").
    assert cast.claim.holder_kind is None
    assert cast.claim.next_action is None
    await app_session.rollback()


async def test_the_fms_chronology_gets_its_ending(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    """Without the ``paid`` event the tracker's external lane stops at "Payment
    processing" and the reader has to infer the rest from the other lane. The
    note carries the reference, because a "Paid" row that does not say what it
    was paid against sends the reader back to the claim header."""
    cast = await _at_fms(app_session, make_user)
    await external.record_external_event(
        app_session, claim_id=cast.claim.id, status=external.PAYMENT_PROCESSING,
        actor_user_id=cast.admin.id, now=NOW,
    )

    await _pay(app_session, cast)

    events = await external.claim_events(app_session, cast.claim.id)
    assert [e.status for e in events] == [
        external.PAYMENT_PROCESSING,
        external.PAID,
    ]
    assert ADA in events[-1].note
    assert events[-1].event_date == PAID_ON
    await app_session.rollback()


async def test_the_traveller_is_told_they_were_paid(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    """Spec §12's "Paid / Settled → Claimant". Only the *Settled* half existed
    before R-7-events, because until now nothing recorded a payment. The
    reference rides the message: it is what a traveller quotes to FMS or their
    bank when the credit is not visible, and they can look it up nowhere else."""
    cast = await _at_fms(app_session, make_user)
    await _pay(app_session, cast)

    rows = list(
        (
            await app_session.execute(
                select(NotificationOutbox).where(
                    NotificationOutbox.meta["kind"].astext == "claim_paid",
                    NotificationOutbox.meta["claim_id"].astext
                    == str(cast.claim.id),
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].meta["recipient_user_id"] == cast.owner.id
    assert ADA in rows[0].meta["body_text"]

    # EXACTLY one message about the payment. The `paid` external event is
    # written by the same call and would otherwise also fire the §12 relay
    # notification — sending a traveller two messages about one payment, the
    # less informative one ("your claim is now Paid", no reference, no amount)
    # arriving first. Found in the R-7-events live smoke rather than by any
    # assertion, because both messages were individually correct.
    everything = list(
        (
            await app_session.execute(
                select(NotificationOutbox).where(
                    NotificationOutbox.meta["claim_id"].astext
                    == str(cast.claim.id)
                )
            )
        )
        .scalars()
        .all()
    )
    assert [row.meta["kind"] for row in everything] == ["claim_paid"]
    await app_session.rollback()


# --- workflow-standards §12 rule 3: the bare verb is refused ----------------


async def test_a_bare_approve_cannot_close_a_claim(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    """The chokepoint. ``lifecycle._assert_payout_recorded`` stops the generic
    action route from reaching a state that asserts FMS paid, and the refusal
    NAMES the route that does the thing rather than leaving an Admin Officer
    holding a button that always fails (§9.1 principle 4)."""
    cast = await _at_fms(app_session, make_user)

    with pytest.raises(APIError) as ei:
        await claim_action(
            app_session, claim_id=cast.claim.id, action="approve",
            actor_user_id=cast.admin.id, now=NOW,
        )
    assert ei.value.code == "reimb_payout_required"
    assert ei.value.details == [
        {"claim_id": cast.claim.id, "action": "mark_paid"}
    ]
    assert cast.claim.status == st.HANDED_TO_FMS
    await app_session.rollback()


async def test_the_action_set_rewrites_approve_into_mark_paid(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    """REWRITTEN, not dropped. The Admin Officer IS authorized to clear this
    gate — they just have to record the payment while doing it — so dropping the
    verb would leave a hole exactly where they need a button. ``return`` (FMS
    bouncing the packet back) is untouched."""
    cast = await _at_fms(app_session, make_user)

    verbs = await claim_actions(
        app_session, claim=cast.claim, actor_user_id=cast.admin.id
    )
    assert MARK_PAID in verbs
    assert "approve" not in verbs
    assert "return" in verbs
    await app_session.rollback()


async def test_the_liquidation_chain_still_gets_settle_not_mark_paid(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    """Two chains, two terminal verbs, one rewrite table. A liquidation records
    a refund receipt against its cash advance; a reimbursement records a payout.
    Mixing them up would offer an Admin Officer a button that files the wrong
    kind of financial record."""
    cast = await _at_fms(app_session, make_user, kind=st.LIQUIDATION_KIND)

    verbs = await claim_actions(
        app_session, claim=cast.claim, actor_user_id=cast.admin.id
    )
    assert SETTLE in verbs
    assert MARK_PAID not in verbs
    await app_session.rollback()


async def test_a_liquidation_cannot_be_marked_paid(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    cast = await _at_fms(app_session, make_user, kind=st.LIQUIDATION_KIND)
    with pytest.raises(APIError) as ei:
        await _pay(app_session, cast)
    assert ei.value.code == "reimb_payout_not_a_reimbursement"
    assert ei.value.details == [{"action": "settle"}]
    await app_session.rollback()


# --- the reference is required ----------------------------------------------


@pytest.mark.parametrize("blank", [None, "", "   "])
async def test_a_claim_cannot_close_without_a_reference(
    app_session, seed_rbac, make_user, reimb_flag_on, blank
):
    """User-confirmed at kickoff: required. ``paid_closed`` is read-only and
    nothing can add the reference afterwards, so a blank one would recreate the
    bare approve this whole increment replaces. The refusal names the honest
    alternative — an Admin Officer without a reference yet can still relay
    'Payment processing', which is true today."""
    cast = await _at_fms(app_session, make_user)
    with pytest.raises(APIError) as ei:
        await _pay(app_session, cast, payout_ref=blank)
    assert ei.value.code == "reimb_payout_ref_required"
    assert "Payment processing" in ei.value.message
    assert cast.claim.status == st.HANDED_TO_FMS
    await app_session.rollback()


async def test_the_payment_date_is_required_and_cannot_be_in_the_future(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    cast = await _at_fms(app_session, make_user)
    with pytest.raises(APIError) as ei:
        await _pay(app_session, cast, paid_on=None)
    assert ei.value.code == "reimb_payout_date_required"

    with pytest.raises(APIError) as ei:
        await _pay(app_session, cast, paid_on=TODAY_MANILA + timedelta(days=1))
    assert ei.value.code == "reimb_external_event_future_date"
    await app_session.rollback()


async def test_paying_twice_is_a_repeat_not_a_race(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    """The ``settlement_already_recorded`` distinction: this sentence is about a
    double tap, not about somebody finishing first, and the difference matters to
    whoever is reading it. It names the reference already on file."""
    cast = await _at_fms(app_session, make_user)
    await _pay(app_session, cast)

    with pytest.raises(APIError) as ei:
        await _pay(app_session, cast, payout_ref="ADA-2026-00999")
    assert ei.value.code == "reimb_payout_already_recorded"
    assert ADA in ei.value.message
    assert cast.claim.payout_ref == ADA  # the first one stands
    await app_session.rollback()


# --- one transaction (workflow-standards §12 rule 1) ------------------------


async def test_a_stale_screen_records_nothing_at_all(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """The reference is written BEFORE the transition (rule 2, so the CAS token
    the client read is still valid at transition time) — which means a refused
    approve has to take the reference down with it. Asserted over HTTP because
    that is where the transaction boundary actually is: the service flushes, the
    router commits, and a 409 must roll the whole thing back.

    Otherwise the claim would sit at ``handed_to_fms`` carrying a payment
    reference for a payment it never recorded, and the double-tap guard would
    then refuse the retry — permanently.
    """
    cast = await _at_fms(app_session, make_user)
    await app_session.commit()

    await login(client, cast.admin, DEFAULT_TEST_PASSWORD)
    stale = await client.post(
        f"{BASE}/claims/{cast.claim.id}/mark-paid",
        json={
            "payout_ref": ADA,
            "paid_on": PAID_ON.isoformat(),
            "expected_version": 999,
        },
        headers=CSRF,
    )
    assert stale.status_code == 409

    fresh = (await client.get(f"{BASE}/claims/{cast.claim.id}")).json()
    assert fresh["status"] == "handed_to_fms"
    assert fresh["payout_ref"] is None
    assert fresh["paid_on"] is None
    assert fresh["latest_external"] is None  # not even the `paid` event


# --- the GRDS retention clock -----------------------------------------------


async def _claim_attachments(app_session, claim_id) -> list[Attachment]:
    return list(
        (
            await app_session.execute(
                select(Attachment).where(
                    Attachment.holder_kind == "reimb_claim",
                    Attachment.holder_id == claim_id,
                )
            )
        )
        .scalars()
        .all()
    )


async def test_paying_starts_the_ten_year_grds_clock(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    """The bug this closes is invisible and total: every claim attachment in the
    system was stored ``retention_starts_at=None`` waiting for "final
    settlement, which is paid_closed (R-7)", and nothing had ever set it. So
    ``retain_until()`` returned None for all of them and the disposal report said
    "retention clock not started" forever."""
    cast = await _at_fms(app_session, make_user)
    files = await _claim_attachments(app_session, cast.claim.id)
    assert files, "the fixture packet should have attached evidence"
    assert all(f.retention_starts_at is None for f in files)

    await _pay(app_session, cast)

    for row in await _claim_attachments(app_session, cast.claim.id):
        await app_session.refresh(row)
        assert row.retention_starts_at == NOW
        # GRDS 2023: DV-supporting records, 10 years from final settlement.
        assert retention.retain_until(
            row.retention_class, row.retention_starts_at
        ) is not None
    await app_session.rollback()


async def test_the_clock_is_never_re_dated(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    """``WHERE retention_starts_at IS NULL`` is what makes the stamp idempotent
    AND what stops a second call pushing a legal retention deadline forward
    invisibly. A file added after the clock started keeps its own NULL until
    somebody starts it deliberately."""
    from office_connect.modules.reimbursement.services import (
        attachments as evidence,
    )

    cast = await _at_fms(app_session, make_user)
    await _pay(app_session, cast)
    stamped = [
        f.retention_starts_at
        for f in await _claim_attachments(app_session, cast.claim.id)
    ]

    later = NOW + timedelta(days=365)
    rows = await evidence.start_retention_clock(
        app_session, claim_id=cast.claim.id, now=later
    )
    assert rows == 0
    assert [
        f.retention_starts_at
        for f in await _claim_attachments(app_session, cast.claim.id)
    ] == stamped
    await app_session.rollback()


async def test_a_cancelled_claim_keeps_its_files_non_disposable(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    """The recorded deferral, pinned so a later change is deliberate rather than
    accidental (user-confirmed at the R-7-events kickoff).

    A voided claim produced no disbursement, so dating a disbursement-record
    retention period from its void would assert a disposal deadline for a payment
    that never happened. The files stay non-disposable — the fail-safe — and stay
    visible in the disposal report as an unanswered question."""
    cast = await standard_cast(app_session, make_user)
    await submit_claim(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.owner.id, now=NOW
    )
    await claim_action(
        app_session, claim_id=cast.claim.id, action="return",
        actor_user_id=cast.approver.id, comment="Withdraw this.",
        reason_ids=[
            (
                await app_session.execute(
                    select(
                        __import__(
                            "office_connect.modules.reimbursement.models",
                            fromlist=["ReimbReturnReasonCatalog"],
                        ).ReimbReturnReasonCatalog.id
                    ).limit(1)
                )
            ).scalar_one()
        ],
        now=NOW,
    )
    await claim_action(
        app_session, claim_id=cast.claim.id, action="cancel",
        actor_user_id=cast.owner.id, comment="Trip did not happen.", now=NOW,
    )
    assert cast.claim.status == st.CANCELLED

    for row in await _claim_attachments(app_session, cast.claim.id):
        assert row.retention_starts_at is None
        assert (
            retention.retain_until(row.retention_class, row.retention_starts_at)
            is None
        )
    await app_session.rollback()


async def test_settling_a_liquidation_starts_the_same_clock(
    app_session, seed_rbac, make_user, reimb_flag_on
):
    """``settled`` is the liquidation chain's final settlement in the literal
    GRDS-2023 sense, so it starts the same 10-year period. Both money terminals
    or neither — a liquidation's evidence is no less a DV support record."""
    cast = await standard_cast(app_session, make_user)
    await apply_reimbursement_seeds(app_session)
    await ensure_reimb_workflow(app_session)
    advance = await ca.create_cash_advance(
        app_session,
        claimant_id=cast.staff.id,
        amount=Decimal("6500.00"),
        actor_user_id=cast.admin.id,
        dv_no="DV-2026-0099",
        dv_date=date(2026, 6, 25),
        dpo_no="DPO-2026-0099",
        date_return=date(2026, 7, 3),
        now=NOW,
    )
    claim = await liq.start_liquidation(
        app_session, cash_advance_id=advance.id,
        actor_user_id=cast.owner.id, now=NOW,
    )
    claim.date_depart = date(2026, 7, 1)
    claim.destination_region_code = "13"
    await make_leg(
        app_session, claim_id=claim.id, seq=1, leg_date=date(2026, 7, 1),
        destination_region_code="13", transport_mode="bus", fare="500.00",
    )
    await make_leg(
        app_session, claim_id=claim.id, seq=2, leg_date=date(2026, 7, 3),
        transport_mode="bus", fare="500.00",
    )
    await satisfy_packet(
        app_session, claim=claim, actor_user_id=cast.owner.id
    )
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
        actor_user_id=cast.admin.id, comment="Certified.", now=NOW,
    )

    await settlement.record_settlement(
        app_session, claim_id=claim.id, actor_user_id=cast.admin.id, now=NOW
    )

    assert claim.status == st.SETTLED
    files = await _claim_attachments(app_session, claim.id)
    assert files
    for row in files:
        await app_session.refresh(row)
        assert row.retention_starts_at == NOW
    await app_session.rollback()


# --- over HTTP --------------------------------------------------------------


async def test_only_an_fms_updater_may_close_a_paid_claim(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """Spec §3.2 gives "Record settlement (refund OR / payout)" to the Admin
    Officer and the System Admin. ``reimb.claim.fms_update`` is the grant the
    whole FMS leg is authorized on — the same permission the ``handed_to_fms``
    gate itself requires, so this check and the engine's ``resolve_authority``
    agree by construction rather than by coincidence."""
    cast = await _at_fms(app_session, make_user)
    await app_session.commit()

    await login(client, cast.owner, DEFAULT_TEST_PASSWORD)
    refused = await client.post(
        f"{BASE}/claims/{cast.claim.id}/mark-paid",
        json={"payout_ref": ADA, "paid_on": PAID_ON.isoformat()},
        headers=CSRF,
    )
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "reimb_external_update_not_permitted"

    await login(client, cast.admin, DEFAULT_TEST_PASSWORD)
    paid = await client.post(
        f"{BASE}/claims/{cast.claim.id}/mark-paid",
        json={"payout_ref": ADA, "paid_on": PAID_ON.isoformat()},
        headers=CSRF,
    )
    assert paid.status_code == 200
    body = paid.json()
    assert body["status"] == "paid_closed"
    assert body["payout_ref"] == ADA
    assert body["available_actions"] == []  # terminal: nothing left to do


async def test_a_paid_claim_leaves_the_oversight_queue(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """The queue answers "what is stuck", so a closed claim belongs in
    R-7-board's Done column rather than in an Admin Officer's working list."""
    cast = await _at_fms(app_session, make_user)
    boss, _ = await make_user()
    await grant_scoped_role(
        app_session, user=boss, role_code="admin_officer", org_unit_id=None
    )
    await app_session.commit()

    # Filtered to this claimant: the suite shares a database and the queue is
    # ordered longest-waiting-first, so an unfiltered page 1 is other tests'
    # leftovers. The filter is what makes the assertion about THIS claim.
    queue = f"{BASE}/claims?claimant_id={cast.staff.id}"

    await login(client, boss, DEFAULT_TEST_PASSWORD)
    before = (await client.get(queue)).json()["items"]
    assert cast.claim.id in [i["id"] for i in before]

    await client.post(
        f"{BASE}/claims/{cast.claim.id}/mark-paid",
        json={"payout_ref": ADA, "paid_on": PAID_ON.isoformat()},
        headers=CSRF,
    )

    after = (await client.get(queue)).json()["items"]
    assert cast.claim.id not in [i["id"] for i in after]
