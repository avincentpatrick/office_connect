"""R-2-wizard — the money step + submit over HTTP, and the other_total
column's resubmit regression (the reason migration 0016 exists).

The full-walk test is the R-2 QA anchor over the wire: the manila_3day trip
computes ₱5,500 per diem + ₱1,000 transport + ₱250 other = ₱6,750 grand, then
submit burns exactly one RB- reference and lands on division_approval."""

from __future__ import annotations

import re
from decimal import Decimal

from sqlalchemy import select

from office_connect.modules.reimbursement.models import ReimbClaim
from office_connect.modules.reimbursement.services import (
    claim_action,
    compute_claim_totals,
    submit_claim,
)
from tests.conftest import CSRF, login
from tests.reimb_lifecycle_helpers import ensure_reimb_workflow, standard_cast, trip_claim
from tests.reimbursement_helpers import make_staff
from tests.workflow_helpers import grant_scoped_role, make_org_unit

BASE = "/api/v1/reimbursement"
REF_RE = re.compile(r"^RB-\d{4}-\d{4}$")


async def _wizard_cast(app_session, make_user):
    """Org tree + claimant login + a division-scoped approver (submit's holder
    resolution needs one) + published definition/seeds, committed."""
    office = await make_org_unit(app_session, kind="office")
    division = await make_org_unit(app_session, kind="division", parent=office)
    staff = await make_staff(app_session, division_id=division.id)
    owner, pw = await make_user(roles=("staff",), staff_id=staff.id)
    approver, _ = await make_user()
    await grant_scoped_role(
        app_session, user=approver, role_code="approver", org_unit_id=division.id
    )
    await ensure_reimb_workflow(app_session)
    await app_session.commit()
    return owner, pw, approver


async def test_http_wizard_walk_computes_the_anchor_and_submits_once(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    owner, pw, approver = await _wizard_cast(app_session, make_user)
    await login(client, owner, pw)

    cid = (await client.post(f"{BASE}/claims", json={}, headers=CSRF)).json()["id"]

    trip = await client.patch(
        f"{BASE}/claims/{cid}",
        json={
            "purpose": "Regional immunization review",
            "destination": "Manila",
            "destination_region_code": "13",
            "date_depart": "2026-07-01",
            "date_return": "2026-07-03",
        },
        headers=CSRF,
    )
    assert trip.status_code == 200, trip.text

    legs = await client.put(
        f"{BASE}/claims/{cid}/legs",
        json={
            "legs": [
                {"leg_date": "2026-07-01", "place": "To Manila",
                 "transport_mode": "bus", "fare": "500.00",
                 "destination_region_code": "13"},
                {"leg_date": "2026-07-03", "place": "Return",
                 "transport_mode": "bus", "fare": "500.00"},
            ]
        },
        headers=CSRF,
    )
    assert legs.status_code == 200, legs.text

    money = await client.patch(
        f"{BASE}/claims/{cid}",
        json={"other_total": "250.00", "fund_source": "GF_ORS"},
        headers=CSRF,
    )
    assert money.status_code == 200, money.text

    computed = await client.post(f"{BASE}/claims/{cid}/compute", headers=CSRF)
    assert computed.status_code == 200, computed.text
    totals = computed.json()["totals"]
    assert totals["per_diem"] == "5500.00"  # the spec §8 worked example
    assert totals["transport"] == "1000.00"
    assert totals["other"] == "250.00"
    assert totals["grand"] == "6750.00"
    assert totals["to_reimburse"] == "6750.00"
    assert len(totals["days"]) == 3
    assert all(
        leg["per_diem_pct"] is not None and leg["leg_total"] is not None
        for leg in computed.json()["legs"]
    )

    submitted = await client.post(f"{BASE}/claims/{cid}/submit", headers=CSRF)
    assert submitted.status_code == 200, submitted.text
    body = submitted.json()
    assert REF_RE.match(body["ref_no"]), body["ref_no"]
    assert body["status"] == "division_approval"
    assert body["status_label"] == "For Approval"
    assert body["next_action"] == "Approve or return"
    assert body["holder_kind"] == "user"

    again = await client.post(f"{BASE}/claims/{cid}/submit", headers=CSRF)
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "reimb_claim_already_submitted"
    # No second reference burned — the ref is unchanged after the 409.
    assert (await client.get(f"{BASE}/claims/{cid}")).json()["ref_no"] == body["ref_no"]


async def test_compute_fail_closed_errors_over_http(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    owner, pw, _ = await _wizard_cast(app_session, make_user)
    await login(client, owner, pw)
    cid = (await client.post(f"{BASE}/claims", json={}, headers=CSRF)).json()["id"]

    # No trip dates, no legs → nothing computable.
    empty = await client.post(f"{BASE}/claims/{cid}/compute", headers=CSRF)
    assert empty.status_code == 422
    assert empty.json()["error"]["code"] == "reimb_no_computable_days"

    await client.patch(
        f"{BASE}/claims/{cid}",
        json={
            "destination_region_code": "13",
            "date_depart": "2026-07-01",
            "date_return": "2026-07-01",
        },
        headers=CSRF,
    )
    await client.put(
        f"{BASE}/claims/{cid}/legs",
        json={
            "legs": [
                {"leg_date": "2026-07-01", "transport_mode": "gov_vehicle",
                 "fare": "100.00"}
            ]
        },
        headers=CSRF,
    )
    gov = await client.post(f"{BASE}/claims/{cid}/compute", headers=CSRF)
    assert gov.status_code == 422
    assert gov.json()["error"]["code"] == "reimb_gov_vehicle_fare"


async def test_patch_clears_totals_only_for_compute_inputs(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """The stale-totals rule in both directions: a display-only edit keeps the
    computed snapshot; a compute-input edit clears it (the FE task list keys
    Money's state off `totals`)."""
    owner, pw, _ = await _wizard_cast(app_session, make_user)
    await login(client, owner, pw)
    cid = (await client.post(f"{BASE}/claims", json={}, headers=CSRF)).json()["id"]
    await client.patch(
        f"{BASE}/claims/{cid}",
        json={
            "destination_region_code": "13",
            "date_depart": "2026-07-01",
            "date_return": "2026-07-03",
        },
        headers=CSRF,
    )
    await client.put(
        f"{BASE}/claims/{cid}/legs",
        json={"legs": [{"leg_date": "2026-07-01", "transport_mode": "bus",
                        "fare": "500.00"}]},
        headers=CSRF,
    )
    assert (
        await client.post(f"{BASE}/claims/{cid}/compute", headers=CSRF)
    ).status_code == 200

    kept = await client.patch(
        f"{BASE}/claims/{cid}", json={"purpose": "cosmetic edit"}, headers=CSRF
    )
    assert kept.json()["totals"] is not None  # display-only field → snapshot kept

    cleared = await client.patch(
        f"{BASE}/claims/{cid}", json={"date_return": "2026-07-04"}, headers=CSRF
    )
    assert cleared.json()["totals"] is None  # compute input → snapshot cleared


async def test_resubmit_of_a_returned_claim_over_http(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """POST /submit on a `returned` claim routes to resubmit: fresh revision,
    same RB reference, persisted other_total intact."""
    from decimal import Decimal as D

    from sqlalchemy import select

    from office_connect.modules.reimbursement.models import ReimbClaim

    owner, pw, approver = await _wizard_cast(app_session, make_user)
    await login(client, owner, pw)
    cid = (await client.post(f"{BASE}/claims", json={}, headers=CSRF)).json()["id"]
    await client.patch(
        f"{BASE}/claims/{cid}",
        json={
            "destination_region_code": "13",
            "date_depart": "2026-07-01",
            "date_return": "2026-07-03",
            "other_total": "250.00",
        },
        headers=CSRF,
    )
    await client.put(
        f"{BASE}/claims/{cid}/legs",
        json={"legs": [{"leg_date": "2026-07-01", "transport_mode": "bus",
                        "fare": "500.00"}]},
        headers=CSRF,
    )
    first = await client.post(f"{BASE}/claims/{cid}/submit", headers=CSRF)
    assert first.status_code == 200, first.text
    ref = first.json()["ref_no"]

    # No return endpoint exists yet (approver surface is next session) — put
    # the claim into `returned` through the sanctioned service path.
    await claim_action(
        app_session, claim_id=cid, action="return",
        actor_user_id=approver.id, comment="Fix the fare",
    )
    await app_session.commit()

    resubmitted = await client.post(f"{BASE}/claims/{cid}/submit", headers=CSRF)
    assert resubmitted.status_code == 200, resubmitted.text
    body = resubmitted.json()
    assert body["status"] == "division_approval"
    assert body["ref_no"] == ref  # a resubmit never burns a new reference
    assert body["totals"]["other"] == "250.00"  # the 0016 regression, over HTTP

    claim = (
        await app_session.execute(select(ReimbClaim).where(ReimbClaim.id == cid))
    ).scalar_one()
    assert claim.other_total == D("250.00")


async def test_submit_requires_ownership_over_http(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    owner, pw, _ = await _wizard_cast(app_session, make_user)
    await login(client, owner, pw)
    cid = (await client.post(f"{BASE}/claims", json={}, headers=CSRF)).json()["id"]

    # Another 'staff' user holds reimb.claim.submit — but is not the owner.
    office = await make_org_unit(app_session, kind="office")
    division = await make_org_unit(app_session, kind="division", parent=office)
    staff = await make_staff(app_session, division_id=division.id)
    intruder, intruder_pw = await make_user(roles=("staff",), staff_id=staff.id)
    await app_session.commit()

    await login(client, intruder, intruder_pw)
    resp = await client.post(f"{BASE}/claims/{cid}/submit", headers=CSRF)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "reimb_not_claim_owner"


async def test_resubmit_keeps_other_total_regression(
    make_user, seed_rbac, app_session, reimb_flag_on
):
    """Migration 0016's reason to exist: before the column, a resubmit
    recomputed without ``other_total`` and silently reset "other" to 0.00.
    Now the column drives every recompute."""
    cast = await standard_cast(app_session, make_user)
    claim = cast.claim
    claim.other_total = Decimal("250.00")
    await app_session.flush()

    await submit_claim(
        app_session, claim_id=claim.id, actor_user_id=cast.owner.id
    )
    assert claim.totals["other"] == "250.00"

    await claim_action(
        app_session,
        claim_id=claim.id,
        action="return",
        actor_user_id=cast.approver.id,
        comment="Receipts missing",
    )
    await claim_action(
        app_session, claim_id=claim.id, action="resubmit",
        actor_user_id=cast.owner.id,
    )
    assert claim.totals["other"] == "250.00"  # pre-fix this read "0.00"
    assert claim.totals["grand"] == "6750.00"


async def test_compute_explicit_param_converges_on_the_column(
    make_user, seed_rbac, app_session
):
    office = await make_org_unit(app_session, kind="office")
    division = await make_org_unit(app_session, kind="division", parent=office)
    staff = await make_staff(app_session, division_id=division.id)
    await ensure_reimb_workflow(app_session)
    claim = await trip_claim(app_session, staff=staff)

    await compute_claim_totals(
        app_session, claim_id=claim.id, other_total=Decimal("99")
    )
    assert claim.other_total == Decimal("99.00")
    assert claim.totals["other"] == "99.00"

    # The parameterless default reads the persisted column.
    await compute_claim_totals(app_session, claim_id=claim.id)
    assert claim.totals["other"] == "99.00"
