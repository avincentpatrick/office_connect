"""R-6-clock QA gate: the cash-advance record, its clock, and who may touch it.

Covers the service (``services/cash_advance.py`` as the single sanctioned writer)
and the HTTP surface (``api/cash_advances.py``). The pure deadline arithmetic
lives in ``test_reimb_liquidation_clock.py``; here the question is whether the
right value gets PINNED, stays pinned, and is visible only to the right people.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from office_connect.modules.reimbursement.models import ReimbCashAdvance
from office_connect.modules.reimbursement.seeds import apply_reimbursement_seeds
from office_connect.modules.reimbursement.services import cash_advance as ca
from office_connect.modules.reimbursement.services import errors
from tests.conftest import CSRF, login, DEFAULT_TEST_PASSWORD
from tests.reimbursement_helpers import make_claim, make_staff
from tests.workflow_helpers import grant_scoped_role, make_org_unit

UTC = timezone.utc
NOW = datetime(2026, 7, 6, 2, 0, tzinfo=UTC)  # Mon 2026-07-06 10:00 Manila
RETURN = date(2026, 7, 3)
DUE = date(2026, 8, 2)  # 30 calendar days after RETURN


@pytest.fixture
async def accounting(app_session, make_user):
    """An office/division tree, a claimant in it, and an Admin Officer whose
    ``reimb.cash_advance.manage`` grant is scoped to the office above them."""
    from types import SimpleNamespace

    await apply_reimbursement_seeds(app_session)
    office = await make_org_unit(app_session, kind="office")
    division = await make_org_unit(app_session, kind="division", parent=office)

    staff = await make_staff(app_session, division_id=division.id)
    owner, _ = await make_user(roles=("staff",), staff_id=staff.id)
    admin, _ = await make_user()
    await grant_scoped_role(
        app_session, user=admin, role_code="admin_officer", org_unit_id=office.id
    )
    await app_session.flush()
    return SimpleNamespace(
        office=office, division=division, staff=staff, owner=owner, admin=admin
    )


# --- The clock is pinned at write time --------------------------------------


async def test_create_pins_the_calendar_deadline(app_session, accounting):
    advance = await ca.create_cash_advance(
        app_session,
        claimant_id=accounting.staff.id,
        amount=Decimal("5000.00"),
        actor_user_id=accounting.admin.id,
        dv_no="DV-2026-0001",
        dv_date=date(2026, 6, 25),
        date_return=RETURN,
        now=NOW,
    )
    assert advance.deadline_date == DUE
    assert advance.deadline_basis == "calendar"
    assert advance.status == "open"


async def test_an_advance_with_no_return_date_has_no_clock(app_session, accounting):
    """A trip that has not happened yet. NULL is the honest answer — the API
    renders 'not started', never a countdown to an invented date."""
    advance = await ca.create_cash_advance(
        app_session,
        claimant_id=accounting.staff.id,
        amount=Decimal("5000.00"),
        actor_user_id=accounting.admin.id,
        now=NOW,
    )
    assert advance.deadline_date is None
    assert advance.deadline_basis is None


async def test_moving_the_return_date_repins_the_deadline(app_session, accounting):
    advance = await ca.create_cash_advance(
        app_session,
        claimant_id=accounting.staff.id,
        amount=Decimal("5000.00"),
        actor_user_id=accounting.admin.id,
        date_return=RETURN,
        now=NOW,
    )
    advance = await ca.update_cash_advance(
        app_session,
        cash_advance_id=advance.id,
        actor_user_id=accounting.admin.id,
        fields={"date_return": date(2026, 7, 10)},
        now=NOW,
    )
    assert advance.deadline_date == date(2026, 8, 9)


async def test_editing_anything_else_leaves_the_clock_alone(app_session, accounting):
    """The R-5-gen discipline, applied to the clock: track which question an
    edit actually answers. A corrected DV number must not silently re-date a
    deadline the traveller was already told."""
    advance = await ca.create_cash_advance(
        app_session,
        claimant_id=accounting.staff.id,
        amount=Decimal("5000.00"),
        actor_user_id=accounting.admin.id,
        date_return=RETURN,
        now=NOW,
    )
    later = NOW + timedelta(days=400)
    advance = await ca.update_cash_advance(
        app_session,
        cash_advance_id=advance.id,
        actor_user_id=accounting.admin.id,
        fields={"dv_no": "DV-CORRECTED", "amount": Decimal("6000.00")},
        now=later,
    )
    assert advance.dv_no == "DV-CORRECTED"
    assert advance.deadline_date == DUE  # untouched, though `now` moved a year


async def test_a_config_change_never_moves_an_existing_deadline(
    app_session, accounting
):
    """Why the column is PINNED and not derived: an admin editing
    ``liquidation.deadline`` changes what NEW advances get, never what an
    in-flight traveller was promised."""
    from office_connect.modules.reimbursement.models import ReimbConfig

    advance = await ca.create_cash_advance(
        app_session,
        claimant_id=accounting.staff.id,
        amount=Decimal("5000.00"),
        actor_user_id=accounting.admin.id,
        date_return=RETURN,
        now=NOW,
    )
    app_session.add(
        ReimbConfig(
            key="liquidation.deadline",
            value={"days": 60, "basis": "calendar"},
            value_display="60 days (test override)",
            source="test",
            effective_from=date(2026, 7, 1),
        )
    )
    await app_session.flush()

    reread = await ca.get_cash_advance(app_session, advance.id)
    assert reread.deadline_date == DUE

    # …but the next advance picks the new rule up.
    other_staff = await make_staff(app_session, division_id=accounting.division.id)
    fresh = await ca.create_cash_advance(
        app_session,
        claimant_id=other_staff.id,
        amount=Decimal("1000.00"),
        actor_user_id=accounting.admin.id,
        date_return=RETURN,
        now=NOW,
    )
    assert fresh.deadline_date == date(2026, 9, 1)


async def test_the_working_basis_is_honoured_end_to_end(app_session, accounting):
    """R-0 closed with a live switch, not a hardcoded answer: flipping the
    seeded config row is all it takes to move every new deadline."""
    from office_connect.modules.reimbursement.models import ReimbConfig

    app_session.add(
        ReimbConfig(
            key="liquidation.deadline",
            value={"days": 30, "basis": "working"},
            value_display="30 working days (test override)",
            source="test",
            effective_from=date(2026, 7, 1),
        )
    )
    await app_session.flush()

    advance = await ca.create_cash_advance(
        app_session,
        claimant_id=accounting.staff.id,
        amount=Decimal("5000.00"),
        actor_user_id=accounting.admin.id,
        date_return=RETURN,
        now=NOW,
    )
    assert advance.deadline_basis == "working"
    assert advance.deadline_date > DUE  # working days always run longer


# --- PD 1445 §89 -------------------------------------------------------------


async def test_a_second_open_advance_is_refused_with_a_sentence(
    app_session, accounting
):
    """The hard-block is a partial-unique DB index (R-1 decision). Without the
    pre-flight it would surface as an IntegrityError → 500, which tells the
    Admin Officer nothing about what to do next."""
    await ca.create_cash_advance(
        app_session,
        claimant_id=accounting.staff.id,
        amount=Decimal("5000.00"),
        actor_user_id=accounting.admin.id,
        dv_no="DV-FIRST",
        date_return=RETURN,
        now=NOW,
    )
    with pytest.raises(Exception) as exc:
        await ca.create_cash_advance(
            app_session,
            claimant_id=accounting.staff.id,
            amount=Decimal("1000.00"),
            actor_user_id=accounting.admin.id,
            now=NOW,
        )
    assert exc.value.code == "reimb_cash_advance_unliquidated"
    assert exc.value.status_code == 409
    assert "DV-FIRST" in exc.value.message
    assert DUE.isoformat() in exc.value.message


async def test_an_overdue_advance_still_holds_the_section_89_slot(
    app_session, accounting
):
    """Going past the deadline is exactly when an advance blocks hardest — the
    index predicate covers 'overdue' for that reason."""
    advance = await ca.create_cash_advance(
        app_session,
        claimant_id=accounting.staff.id,
        amount=Decimal("5000.00"),
        actor_user_id=accounting.admin.id,
        date_return=RETURN,
        now=NOW,
    )
    assert await ca.mark_overdue(app_session, cash_advance=advance) is True
    with pytest.raises(Exception) as exc:
        await ca.create_cash_advance(
            app_session,
            claimant_id=accounting.staff.id,
            amount=Decimal("1000.00"),
            actor_user_id=accounting.admin.id,
            now=NOW,
        )
    assert exc.value.code == "reimb_cash_advance_unliquidated"


async def test_a_settled_advance_frees_the_slot(app_session, accounting):
    advance = await ca.create_cash_advance(
        app_session,
        claimant_id=accounting.staff.id,
        amount=Decimal("5000.00"),
        actor_user_id=accounting.admin.id,
        date_return=RETURN,
        now=NOW,
    )
    advance.status = "settled"
    await app_session.flush()

    second = await ca.create_cash_advance(
        app_session,
        claimant_id=accounting.staff.id,
        amount=Decimal("1000.00"),
        actor_user_id=accounting.admin.id,
        now=NOW,
    )
    assert second.id != advance.id


async def test_a_settled_advance_cannot_be_edited(app_session, accounting):
    """A closed financial record. Reopening one is a reversal with its own
    authority story, not a PATCH."""
    advance = await ca.create_cash_advance(
        app_session,
        claimant_id=accounting.staff.id,
        amount=Decimal("5000.00"),
        actor_user_id=accounting.admin.id,
        now=NOW,
    )
    advance.status = "settled"
    await app_session.flush()
    with pytest.raises(Exception) as exc:
        await ca.update_cash_advance(
            app_session,
            cash_advance_id=advance.id,
            actor_user_id=accounting.admin.id,
            fields={"dv_no": "X"},
            now=NOW,
        )
    assert exc.value.code == "reimb_cash_advance_settled"


# --- Validation --------------------------------------------------------------


async def test_a_zero_advance_is_refused(app_session, accounting):
    with pytest.raises(Exception) as exc:
        await ca.create_cash_advance(
            app_session,
            claimant_id=accounting.staff.id,
            amount=Decimal("0.00"),
            actor_user_id=accounting.admin.id,
            now=NOW,
        )
    assert exc.value.code == "reimb_cash_advance_amount_invalid"


async def test_a_return_before_the_dv_date_is_refused(app_session, accounting):
    """An advance cannot be liquidated before it was issued."""
    with pytest.raises(Exception) as exc:
        await ca.create_cash_advance(
            app_session,
            claimant_id=accounting.staff.id,
            amount=Decimal("5000.00"),
            actor_user_id=accounting.admin.id,
            dv_date=date(2026, 7, 10),
            date_return=date(2026, 7, 3),
            now=NOW,
        )
    assert exc.value.code == "reimb_cash_advance_dates_invalid"


# --- The claim mirror --------------------------------------------------------


async def test_linking_a_claim_mirrors_the_deadline(app_session, accounting):
    advance = await ca.create_cash_advance(
        app_session,
        claimant_id=accounting.staff.id,
        amount=Decimal("5000.00"),
        actor_user_id=accounting.admin.id,
        date_return=RETURN,
        now=NOW,
    )
    claim = await make_claim(app_session, claimant_id=accounting.staff.id)
    await ca.link_claim(app_session, claim=claim, cash_advance=advance)
    assert claim.cash_advance_id == advance.id
    assert claim.liquidation_deadline == DUE


async def test_a_moved_deadline_re_mirrors_onto_linked_claims(
    app_session, accounting
):
    advance = await ca.create_cash_advance(
        app_session,
        claimant_id=accounting.staff.id,
        amount=Decimal("5000.00"),
        actor_user_id=accounting.admin.id,
        date_return=RETURN,
        now=NOW,
    )
    claim = await make_claim(app_session, claimant_id=accounting.staff.id)
    await ca.link_claim(app_session, claim=claim, cash_advance=advance)

    advance = await ca.update_cash_advance(
        app_session,
        cash_advance_id=advance.id,
        actor_user_id=accounting.admin.id,
        fields={"date_return": date(2026, 7, 10)},
        now=NOW,
    )
    updated = await ca.remirror_deadline(app_session, cash_advance=advance)
    assert updated == 1
    assert claim.liquidation_deadline == date(2026, 8, 9)


async def test_re_dating_clears_a_stale_overdue_verdict(app_session, accounting):
    """The overdue flag was a statement about the OLD deadline. Leaving it would
    show a red badge on an advance that is now comfortably on track."""
    advance = await ca.create_cash_advance(
        app_session,
        claimant_id=accounting.staff.id,
        amount=Decimal("5000.00"),
        actor_user_id=accounting.admin.id,
        date_return=RETURN,
        now=NOW,
    )
    await ca.mark_overdue(app_session, cash_advance=advance)
    advance = await ca.update_cash_advance(
        app_session,
        cash_advance_id=advance.id,
        actor_user_id=accounting.admin.id,
        fields={"date_return": date(2026, 9, 1)},
        now=NOW,
    )
    assert advance.status == "open"


# --- HTTP surface: authorization -------------------------------------------


@pytest.fixture
async def http(client, app_session, accounting):
    """Committed cast + a logged-in HTTP client factory."""
    await app_session.commit()

    async def _as(user):
        resp = await login(client, user, DEFAULT_TEST_PASSWORD)
        assert resp.status_code == 200, resp.text
        return client

    return _as


async def test_accounting_can_record_an_advance_over_http(
    http, accounting, reimb_flag_on
):
    c = await http(accounting.admin)
    resp = await c.post(
        "/api/v1/reimbursement/cash-advances",
        json={
            "claimant_id": accounting.staff.id,
            "amount": "5000.00",
            "dv_no": "DV-HTTP-1",
            "date_return": RETURN.isoformat(),
        },
        headers=CSRF,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["deadline_date"] == DUE.isoformat()
    assert body["deadline_basis"] == "calendar"
    assert body["status_label"] == "Open"
    assert body["amount"] == "5000.00"
    # The countdown is server-derived — the client is never handed the job.
    assert body["days_remaining"] is not None
    assert body["deadline_state"] in ("on_track", "due_soon", "overdue")


async def test_a_claimant_cannot_record_their_own_advance(
    http, accounting, reimb_flag_on
):
    """Recording is Accounting's act — dv_no/dv_date are data only Accounting
    holds, and a self-declared advance would make the §89 block optional."""
    c = await http(accounting.owner)
    resp = await c.post(
        "/api/v1/reimbursement/cash-advances",
        json={"claimant_id": accounting.staff.id, "amount": "5000.00"},
        headers=CSRF,
    )
    assert resp.status_code == 403


async def test_a_claimant_reads_their_own_advances(http, accounting, reimb_flag_on):
    admin_client = await http(accounting.admin)
    await admin_client.post(
        "/api/v1/reimbursement/cash-advances",
        json={
            "claimant_id": accounting.staff.id,
            "amount": "5000.00",
            "date_return": RETURN.isoformat(),
        },
        headers=CSRF,
    )
    c = await http(accounting.owner)
    resp = await c.get("/api/v1/reimbursement/cash-advances", headers=CSRF)
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["claimant_id"] == accounting.staff.id


async def test_a_stranger_cannot_read_someone_elses_advance(
    http, app_session, accounting, make_user, reimb_flag_on
):
    """The `staff` role's read grant is GLOBAL (spec §3.2), so the route gate
    alone would publish every colleague's DV numbers and peso amounts."""
    admin_client = await http(accounting.admin)
    created = await admin_client.post(
        "/api/v1/reimbursement/cash-advances",
        json={"claimant_id": accounting.staff.id, "amount": "5000.00"},
        headers=CSRF,
    )
    advance_id = created.json()["id"]

    other_staff = await make_staff(app_session)
    stranger, _ = await make_user(roles=("staff",), staff_id=other_staff.id)
    await app_session.commit()

    c = await http(stranger)
    resp = await c.get(
        f"/api/v1/reimbursement/cash-advances/{advance_id}", headers=CSRF
    )
    assert resp.status_code == 403


async def test_the_section_89_block_is_a_409_over_http(
    http, accounting, reimb_flag_on
):
    c = await http(accounting.admin)
    payload = {
        "claimant_id": accounting.staff.id,
        "amount": "5000.00",
        "dv_no": "DV-FIRST",
        "date_return": RETURN.isoformat(),
    }
    assert (
        await c.post(
            "/api/v1/reimbursement/cash-advances", json=payload, headers=CSRF
        )
    ).status_code == 201
    resp = await c.post(
        "/api/v1/reimbursement/cash-advances",
        json={"claimant_id": accounting.staff.id, "amount": "100.00"},
        headers=CSRF,
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "reimb_cash_advance_unliquidated"
    assert "DV-FIRST" in resp.json()["error"]["message"]


async def test_a_client_cannot_post_its_own_deadline(http, accounting, reimb_flag_on):
    """The clock is server-computed. A client that could post a deadline could
    post one COA never gave — the same doctrine as money (api-standards §2)."""
    c = await http(accounting.admin)
    resp = await c.post(
        "/api/v1/reimbursement/cash-advances",
        json={
            "claimant_id": accounting.staff.id,
            "amount": "5000.00",
            "date_return": RETURN.isoformat(),
            "deadline_date": "2099-01-01",
            "status": "settled",
        },
        headers=CSRF,
    )
    assert resp.status_code == 201
    assert resp.json()["deadline_date"] == DUE.isoformat()
    assert resp.json()["status"] == "open"


async def test_the_advance_is_audited_with_its_actor(app_session, accounting):
    """Standing rule 5 — the hash-chained ``core_audit_logs`` trail is what
    records WHO recorded a financial fact COA will later ask about.

    Asserted against the audit log, not ``created_by``: the ownership columns
    exist on every business table but nothing on the platform populates them
    today (0 of ~1,450 live ``reimb_claims`` rows carry one). That is a
    foundation-level gap, not this increment's — recorded in the module doc
    rather than quietly widened into here.
    """
    from office_connect.core.models import AuditLog

    advance = await ca.create_cash_advance(
        app_session,
        claimant_id=accounting.staff.id,
        amount=Decimal("5000.00"),
        actor_user_id=accounting.admin.id,
        date_return=RETURN,
        now=NOW,
    )
    await app_session.commit()

    entries = (
        (
            await app_session.execute(
                select(AuditLog).where(
                    AuditLog.table_name == "reimb_cash_advances",
                    AuditLog.row_pk == advance.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert entries, "recording a cash advance must leave an audit row"
    insert = next(e for e in entries if e.action == "insert")
    assert insert.actor_id == accounting.admin.id
    # The clock is part of what was asserted, so it must be in the trail.
    assert insert.new_data["deadline_date"] == DUE.isoformat()
    assert insert.new_data["deadline_basis"] == "calendar"
