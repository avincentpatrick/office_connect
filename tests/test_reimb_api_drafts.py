"""R-2-wizard — draft CRUD over HTTP: create/prefill, PATCH, legs, cancel,
and the spec §3.2 read-scoping matrix (claims are NOT bureau-public)."""

from __future__ import annotations

from sqlalchemy import select

from office_connect.modules.reimbursement.models import (
    ReimbClaim,
    ReimbItineraryLeg,
    ReimbStatusHistory,
)
from office_connect.modules.reimbursement.services import lifecycle
from tests.conftest import CSRF, login
from tests.reimb_lifecycle_helpers import standard_cast
from tests.reimbursement_helpers import make_staff
from tests.workflow_helpers import grant_scoped_role, make_org_unit

BASE = "/api/v1/reimbursement"


async def _staff_user(app_session, make_user, *, employment_status="permanent"):
    """An org-united staff row + its linked 'staff'-role login, committed."""
    office = await make_org_unit(app_session, kind="office")
    division = await make_org_unit(app_session, kind="division", parent=office)
    staff = await make_staff(
        app_session, division_id=division.id, employment_status=employment_status
    )
    user, pw = await make_user(roles=("staff",), staff_id=staff.id)
    await app_session.commit()
    return office, division, staff, user, pw


async def test_create_draft_prefills_and_stamps_the_read_model(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    _, division, staff, user, pw = await _staff_user(app_session, make_user)
    staff_name, division_name = staff.full_name, division.name
    await login(client, user, pw)

    resp = await client.post(f"{BASE}/claims", json={}, headers=CSRF)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "draft"
    assert body["status_label"] == "Draft"
    assert body["next_action"] == "Complete your packet"
    assert body["claimant"]["full_name"] == staff_name
    assert body["claimant"]["division"]["name"] == division_name
    assert body["is_jo_cos"] is False
    assert body["other_total"] == "0.00"
    assert body["totals"] is None
    assert body["legs"] == []
    assert body["ref_no"] is None  # RB- numbers are burned only at submit

    claim = (
        await app_session.execute(
            select(ReimbClaim).where(ReimbClaim.id == body["id"])
        )
    ).scalar_one()
    assert claim.status == "draft"
    assert claim.holder_kind == "user" and claim.holder_id == user.id
    assert claim.holder_since is not None
    assert claim.next_action == "Complete your packet"
    history = (
        (
            await app_session.execute(
                select(ReimbStatusHistory).where(
                    ReimbStatusHistory.claim_id == claim.id
                )
            )
        )
        .scalars()
        .all()
    )
    assert [(h.from_status, h.to_status) for h in history] == [(None, "draft")]


async def test_create_draft_accepts_prefill_and_derives_jo_cos(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    _, _, _, user, pw = await _staff_user(
        app_session, make_user, employment_status="job_order"
    )
    await login(client, user, pw)

    resp = await client.post(
        f"{BASE}/claims",
        json={"purpose": "Immunization review", "destination_region_code": "13"},
        headers=CSRF,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["is_jo_cos"] is True
    assert body["purpose"] == "Immunization review"
    assert body["destination_region_code"] == "13"


async def test_create_draft_requires_a_staff_link(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    user, pw = await make_user(roles=("staff",))  # no staff_id
    await login(client, user, pw)
    resp = await client.post(f"{BASE}/claims", json={}, headers=CSRF)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "reimb_no_staff_link"


async def test_patch_persists_business_fields(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    _, _, _, user, pw = await _staff_user(app_session, make_user)
    await login(client, user, pw)
    cid = (await client.post(f"{BASE}/claims", json={}, headers=CSRF)).json()["id"]

    resp = await client.patch(
        f"{BASE}/claims/{cid}",
        json={
            "dpo_no": "DPO-2026-077",
            "dpo_date": "2026-06-20",
            "purpose": "Regional workshop",
            "destination": "Manila",
            "destination_region_code": "13",
            "date_depart": "2026-07-01",
            "date_return": "2026-07-03",
            "is_within_50km": False,
            "overnight_stay": True,
            "fund_source": "GF_ORS",
            "other_total": "250.00",
        },
        headers=CSRF,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["other_total"] == "250.00"
    assert body["fund_source"] == "GF_ORS"
    assert body["overnight_stay"] is True
    assert body["date_depart"] == "2026-07-01"

    # Round-trips on a fresh GET too (persisted, not echoed).
    got = (await client.get(f"{BASE}/claims/{cid}")).json()
    assert got["other_total"] == "250.00"
    assert got["dpo_no"] == "DPO-2026-077"


async def test_patch_guards_ownership_dates_and_activity(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    _, _, _, user, pw = await _staff_user(app_session, make_user)
    await login(client, user, pw)
    cid = (await client.post(f"{BASE}/claims", json={}, headers=CSRF)).json()["id"]

    bad_dates = await client.patch(
        f"{BASE}/claims/{cid}",
        json={"date_depart": "2026-07-03", "date_return": "2026-07-01"},
        headers=CSRF,
    )
    assert bad_dates.status_code == 422
    assert bad_dates.json()["error"]["code"] == "reimb_invalid_trip_dates"

    bad_activity = await client.patch(
        f"{BASE}/claims/{cid}", json={"activity_id": 99999999}, headers=CSRF
    )
    assert bad_activity.status_code == 422
    assert bad_activity.json()["error"]["code"] == "reimb_unknown_activity"

    # A second staff user (global reimb.claim.create grant!) is not the owner.
    _, _, _, other, other_pw = await _staff_user(app_session, make_user)
    await login(client, other, other_pw)
    denied = await client.patch(
        f"{BASE}/claims/{cid}", json={"purpose": "hijack"}, headers=CSRF
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "reimb_not_claim_owner"


async def test_patch_after_submit_is_409(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    cast = await standard_cast(app_session, make_user)
    await app_session.commit()
    await lifecycle.submit_claim(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.owner.id
    )
    await app_session.commit()

    owner_pw = "correct-horse-battery-staple"
    await login(client, cast.owner, owner_pw)
    resp = await client.patch(
        f"{BASE}/claims/{cast.claim.id}", json={"purpose": "late edit"}, headers=CSRF
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "reimb_claim_not_editable"


async def test_legs_replace_assigns_seq_and_soft_deletes(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    _, _, _, user, pw = await _staff_user(app_session, make_user)
    await login(client, user, pw)
    cid = (await client.post(f"{BASE}/claims", json={}, headers=CSRF)).json()["id"]

    first = await client.put(
        f"{BASE}/claims/{cid}/legs",
        json={
            "legs": [
                {"leg_date": "2026-07-01", "place": "Manila", "transport_mode": "bus",
                 "fare": "500.00", "destination_region_code": "13"},
                {"leg_date": "2026-07-03", "place": "Return", "transport_mode": "bus",
                 "fare": "500.00"},
            ]
        },
        headers=CSRF,
    )
    assert first.status_code == 200, first.text
    legs = first.json()["legs"]
    assert [leg["seq"] for leg in legs] == [1, 2]
    keep_id, drop_id = legs[0]["id"], legs[1]["id"]

    # Simulate a computed column so the replace provably nulls it.
    row = (
        await app_session.execute(
            select(ReimbItineraryLeg).where(ReimbItineraryLeg.id == keep_id)
        )
    ).scalar_one()
    row.per_diem_pct = 100
    await app_session.commit()

    second = await client.put(
        f"{BASE}/claims/{cid}/legs",
        json={
            "legs": [
                {"id": keep_id, "leg_date": "2026-07-01", "place": "Manila (edited)",
                 "transport_mode": "taxi", "fare": "350.00",
                 "destination_region_code": "13"},
                {"leg_date": "2026-07-02", "place": "Fieldwork",
                 "transport_mode": "ride_hail", "fare": "120.00"},
            ]
        },
        headers=CSRF,
    )
    assert second.status_code == 200, second.text
    new_legs = second.json()["legs"]
    assert [leg["seq"] for leg in new_legs] == [1, 2]
    assert new_legs[0]["id"] == keep_id
    assert new_legs[0]["place"] == "Manila (edited)"
    assert new_legs[0]["per_diem_pct"] is None  # stale money never survives
    assert all(leg["id"] != drop_id for leg in new_legs)

    # The dropped leg is SOFT-deleted (rule 6) — still on disk, tombstoned.
    dropped = (
        await app_session.execute(
            select(ReimbItineraryLeg)
            .where(ReimbItineraryLeg.id == drop_id)
            .execution_options(include_deleted=True)
        )
    ).scalar_one()
    assert dropped.deleted_at is not None
    assert dropped.deleted_by == user.id


async def test_legs_replace_rejects_a_foreign_leg_id(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    _, _, _, user, pw = await _staff_user(app_session, make_user)
    await login(client, user, pw)
    cid_a = (await client.post(f"{BASE}/claims", json={}, headers=CSRF)).json()["id"]
    cid_b = (await client.post(f"{BASE}/claims", json={}, headers=CSRF)).json()["id"]
    leg_b = (
        await client.put(
            f"{BASE}/claims/{cid_b}/legs",
            json={"legs": [{"leg_date": "2026-07-01", "transport_mode": "bus"}]},
            headers=CSRF,
        )
    ).json()["legs"][0]["id"]

    resp = await client.put(
        f"{BASE}/claims/{cid_a}/legs",
        json={"legs": [{"id": leg_b, "leg_date": "2026-07-01"}]},
        headers=CSRF,
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "reimb_leg_unknown"


async def test_cancel_draft_over_http(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    _, _, _, user, pw = await _staff_user(app_session, make_user)
    await login(client, user, pw)
    cid = (await client.post(f"{BASE}/claims", json={}, headers=CSRF)).json()["id"]

    empty = await client.post(
        f"{BASE}/claims/{cid}/cancel", json={"comment": ""}, headers=CSRF
    )
    assert empty.status_code == 422  # pydantic min_length → validation_error

    resp = await client.post(
        f"{BASE}/claims/{cid}/cancel",
        json={"comment": "Trip cancelled by the division"},
        headers=CSRF,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "cancelled"
    assert body["status_label"] == "Cancelled/Void"
    assert body["next_action"] is None
    assert body["holder_kind"] is None

    history = (
        (
            await app_session.execute(
                select(ReimbStatusHistory)
                .where(ReimbStatusHistory.claim_id == cid)
                .order_by(ReimbStatusHistory.id)
            )
        )
        .scalars()
        .all()
    )
    assert [(h.from_status, h.to_status) for h in history] == [
        (None, "draft"),
        ("draft", "cancelled"),
    ]

    # Double-cancel must not append a no-op cancelled→cancelled history row.
    again = await client.post(
        f"{BASE}/claims/{cid}/cancel", json={"comment": "again"}, headers=CSRF
    )
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "reimb_claim_cancelled"

    # A cancelled claim is terminal — submit cannot resurrect it (and must
    # never burn an RB reference for it).
    revive = await client.post(f"{BASE}/claims/{cid}/submit", headers=CSRF)
    assert revive.status_code == 409
    assert revive.json()["error"]["code"] == "reimb_claim_cancelled"
    assert (await client.get(f"{BASE}/claims/{cid}")).json()["ref_no"] is None


async def test_cancel_after_submit_is_409(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    cast = await standard_cast(app_session, make_user)
    await app_session.commit()
    await lifecycle.submit_claim(
        app_session, claim_id=cast.claim.id, actor_user_id=cast.owner.id
    )
    await app_session.commit()

    await login(client, cast.owner, "correct-horse-battery-staple")
    resp = await client.post(
        f"{BASE}/claims/{cast.claim.id}/cancel",
        json={"comment": "too late"},
        headers=CSRF,
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "reimb_claim_already_submitted"


async def test_read_scope_matrix_not_bureau_public(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """Spec §3.2: owner sees own; scoped approver/admin see their unit; a plain
    staff user — whose role DOES hold a global ``reimb.claim.read`` grant —
    still cannot read someone else's claim; system_admin sees all."""
    import pyotp

    cast = await standard_cast(app_session, make_user)
    sibling = await make_org_unit(app_session, kind="division", parent=cast.office)
    outsider, outsider_pw = await make_user(roles=("staff",))
    # The approver role demands MFA at login (mfa_required_role_codes) — enroll
    # login-capable approver/sysadmin users up front.
    div_secret, sib_secret, sys_secret = (pyotp.random_base32() for _ in range(3))
    division_approver, div_pw = await make_user(
        mfa_enabled=True, mfa_secret=div_secret
    )
    await grant_scoped_role(
        app_session, user=division_approver, role_code="approver",
        org_unit_id=cast.division.id,
    )
    sibling_approver, sib_pw = await make_user(
        mfa_enabled=True, mfa_secret=sib_secret
    )
    await grant_scoped_role(
        app_session, user=sibling_approver, role_code="approver",
        org_unit_id=sibling.id,
    )
    sysadmin, sys_pw = await make_user(
        roles=("system_admin",), mfa_enabled=True, mfa_secret=sys_secret
    )
    await app_session.commit()
    pw = "correct-horse-battery-staple"
    url = f"{BASE}/claims/{cast.claim.id}"

    await login(client, cast.owner, pw)
    assert (await client.get(url)).status_code == 200

    await login(client, outsider, outsider_pw)
    denied = await client.get(url)
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "reimb_not_claim_owner"

    await login(client, division_approver, div_pw, div_secret)
    assert (await client.get(url)).status_code == 200  # division-scoped

    await login(client, sibling_approver, sib_pw, sib_secret)
    assert (await client.get(url)).status_code == 403  # wrong division

    await login(client, cast.admin, pw)
    assert (await client.get(url)).status_code == 200  # office-scoped admin

    await login(client, sysadmin, sys_pw, sys_secret)
    assert (await client.get(url)).status_code == 200  # global grants
