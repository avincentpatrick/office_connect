"""R-2-wizard — the My-Work inbox (spec §7 rule 3) + the regions reference
endpoint. Membership is holder/claimant-keyed: nothing leaks across users."""

from __future__ import annotations

from tests.conftest import CSRF, login
from tests.reimb_checklist_helpers import satisfy_packet_over_http
from tests.reimb_lifecycle_helpers import ensure_reimb_workflow
from tests.reimbursement_helpers import make_staff
from tests.workflow_helpers import grant_scoped_role, make_org_unit

BASE = "/api/v1/reimbursement"


async def _staff_user(app_session, make_user):
    office = await make_org_unit(app_session, kind="office")
    division = await make_org_unit(app_session, kind="division", parent=office)
    staff = await make_staff(app_session, division_id=division.id)
    user, pw = await make_user(roles=("staff",), staff_id=staff.id)
    await app_session.commit()
    return division, staff, user, pw


async def test_fresh_draft_waits_on_its_owner(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    _, _, user, pw = await _staff_user(app_session, make_user)
    await login(client, user, pw)
    created = (await client.post(f"{BASE}/claims", json={}, headers=CSRF)).json()

    work = (await client.get(f"{BASE}/my-work")).json()
    waiting_ids = [item["id"] for item in work["waiting_on_you"]]
    assert created["id"] in waiting_ids
    item = next(i for i in work["waiting_on_you"] if i["id"] == created["id"])
    assert item["status"] == "draft"
    assert item["next_action"] == "Complete your packet"
    assert item["holder_display"] == "You"
    assert item["days_in_state"] == 0
    assert created["id"] not in [i["id"] for i in work["in_flight"]]
    # A draft has no gate step, so no SLA — the badge is approver-facing only
    # (spec §6.3; the claimant's clock is the R-6 liquidation deadline).
    assert item["sla_due_at"] is None
    assert item["sla_state"] is None


async def test_submit_moves_the_claim_to_in_flight_and_the_approver_queue(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    import pyotp

    division, staff, owner, pw = await _staff_user(app_session, make_user)
    # The approver role demands MFA at login — enroll up front.
    approver_secret = pyotp.random_base32()
    approver, approver_pw = await make_user(
        mfa_enabled=True, mfa_secret=approver_secret
    )
    await grant_scoped_role(
        app_session, user=approver, role_code="approver", org_unit_id=division.id
    )
    await ensure_reimb_workflow(app_session)
    await app_session.commit()

    await login(client, owner, pw)
    cid = (await client.post(f"{BASE}/claims", json={}, headers=CSRF)).json()["id"]
    await client.patch(
        f"{BASE}/claims/{cid}",
        json={
            "purpose": "Site visit",
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
    # The 5th wizard step (R-3): submit refuses an incomplete packet.
    await satisfy_packet_over_http(client, cid)
    submitted = await client.post(f"{BASE}/claims/{cid}/submit", headers=CSRF)
    assert submitted.status_code == 200, submitted.text

    owner_work = (await client.get(f"{BASE}/my-work")).json()
    assert cid not in [i["id"] for i in owner_work["waiting_on_you"]]
    flight = next(i for i in owner_work["in_flight"] if i["id"] == cid)
    assert flight["status"] == "division_approval"
    assert flight["next_action"] == "Approve or return"
    assert flight["holder_display"] == approver.email  # approver has no staff row
    assert flight["grand"] is not None
    assert flight["days_in_state"] >= 0

    await login(client, approver, approver_pw, approver_secret)
    approver_work = (await client.get(f"{BASE}/my-work")).json()
    assert cid in [i["id"] for i in approver_work["waiting_on_you"]]
    assert approver_work["in_flight"] == []  # no staff link → owns nothing

    # R-4-screens closed the SLA-badge deferral: a freshly activated gate step
    # carries a due date (3 Manila working days out), so the row is on track.
    queued = next(i for i in approver_work["waiting_on_you"] if i["id"] == cid)
    assert queued["sla_due_at"] is not None
    assert queued["sla_state"] == "on_track"


async def test_waiting_orders_longest_waiting_first(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    _, _, user, pw = await _staff_user(app_session, make_user)
    await login(client, user, pw)
    first = (await client.post(f"{BASE}/claims", json={}, headers=CSRF)).json()["id"]
    second = (await client.post(f"{BASE}/claims", json={}, headers=CSRF)).json()["id"]

    work = (await client.get(f"{BASE}/my-work")).json()
    ids = [i["id"] for i in work["waiting_on_you"] if i["id"] in (first, second)]
    assert ids == [first, second]  # holder_since ASC, id ASC tie-break


async def test_my_work_never_leaks_across_users(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    _, _, user_a, pw_a = await _staff_user(app_session, make_user)
    await login(client, user_a, pw_a)
    cid = (await client.post(f"{BASE}/claims", json={}, headers=CSRF)).json()["id"]

    _, _, user_b, pw_b = await _staff_user(app_session, make_user)
    await login(client, user_b, pw_b)
    work = (await client.get(f"{BASE}/my-work")).json()
    assert cid not in [i["id"] for i in work["waiting_on_you"]]
    assert cid not in [i["id"] for i in work["in_flight"]]


async def test_terminal_claims_leave_both_lists(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    _, _, user, pw = await _staff_user(app_session, make_user)
    await login(client, user, pw)
    cid = (await client.post(f"{BASE}/claims", json={}, headers=CSRF)).json()["id"]
    cancelled = await client.post(
        f"{BASE}/claims/{cid}/cancel", json={"comment": "no longer needed"},
        headers=CSRF,
    )
    assert cancelled.status_code == 200

    work = (await client.get(f"{BASE}/my-work")).json()
    assert cid not in [i["id"] for i in work["waiting_on_you"]]
    assert cid not in [i["id"] for i in work["in_flight"]]


async def test_regions_serves_the_effective_cluster_map(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    _, _, user, pw = await _staff_user(app_session, make_user)
    await ensure_reimb_workflow(app_session)  # applies the module seeds
    await app_session.commit()
    await login(client, user, pw)

    resp = await client.get(f"{BASE}/regions")
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert rows, "expected the seeded PSGC region → cluster map"
    codes = [r["region_code"] for r in rows]
    assert len(codes) == len(set(codes))  # one row per region (latest effective)
    assert "13" in codes  # NCR
    assert all(r["cluster"] in {"I", "II", "III"} for r in rows)
