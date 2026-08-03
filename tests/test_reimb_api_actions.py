"""R-4-screens — the approver's decision endpoints (the module's un-gated pair).

What this pins:

- the whole chain now moves over HTTP (``division_approval → admin_review →
  handed_to_fms → paid_closed``) — before this increment a submitted claim could
  only be acted on from a Python shell;
- ``ClaimDetail.available_actions`` is per-actor and is what the UI renders
  (workflow-standards §3 — the client never computes permissions);
- ≥1 taxonomy reason on return, at BOTH layers: the wire schema (a field-anchored
  422 the FE maps onto the reason picker) and the service (junk ids rejected);
- the CAS token round-trips: a stale ``expected_version`` 409s rather than acting
  on a screen that has moved;
- segregation is filtered OUT of ``available_actions``, not just enforced on POST —
  a button that is certain to 409 must never render.
"""

from __future__ import annotations

import pyotp
from sqlalchemy import select

from office_connect.modules.reimbursement.models import ReimbReturnEvent
from tests.conftest import CSRF, login
from tests.reimb_lifecycle_helpers import ensure_reimb_workflow
from tests.reimbursement_helpers import make_staff
from tests.workflow_helpers import grant_scoped_role, make_org_unit

BASE = "/api/v1/reimbursement"


async def _mfa_user(make_user):
    """Approver/admin roles demand MFA at login — enroll up front."""
    secret = pyotp.random_base32()
    user, pw = await make_user(mfa_enabled=True, mfa_secret=secret)
    return user, pw, secret


async def _submitted_over_http(client, app_session, make_user):
    """The full cast with a claim sitting in ``division_approval``, driven
    entirely through the wizard endpoints (no service-layer shortcuts)."""
    office = await make_org_unit(app_session, kind="office")
    division = await make_org_unit(app_session, kind="division", parent=office)
    staff = await make_staff(app_session, division_id=division.id)
    owner, owner_pw = await make_user(roles=("staff",), staff_id=staff.id)

    approver, approver_pw, approver_secret = await _mfa_user(make_user)
    await grant_scoped_role(
        app_session, user=approver, role_code="approver", org_unit_id=division.id
    )
    admin, admin_pw, admin_secret = await _mfa_user(make_user)
    await grant_scoped_role(
        app_session, user=admin, role_code="admin_officer", org_unit_id=office.id
    )
    await ensure_reimb_workflow(app_session)
    await app_session.commit()

    await login(client, owner, owner_pw)
    cid = (await client.post(f"{BASE}/claims", json={}, headers=CSRF)).json()["id"]
    await client.patch(
        f"{BASE}/claims/{cid}",
        json={
            "purpose": "Regional immunization review",
            "destination": "Butuan City",
            "destination_region_code": "13",
            "date_depart": "2026-07-01",
            "date_return": "2026-07-03",
        },
        headers=CSRF,
    )
    await client.put(
        f"{BASE}/claims/{cid}/legs",
        json={
            "legs": [
                {"leg_date": "2026-07-01", "transport_mode": "bus", "fare": "500.00"}
            ]
        },
        headers=CSRF,
    )
    submitted = await client.post(f"{BASE}/claims/{cid}/submit", headers=CSRF)
    assert submitted.status_code == 200, submitted.text

    return {
        "claim_id": cid,
        "owner": (owner, owner_pw, None),
        "approver": (approver, approver_pw, approver_secret),
        "admin": (admin, admin_pw, admin_secret),
    }


async def _reason_ids(client, *, limit=1):
    reasons = (await client.get(f"{BASE}/return-reasons")).json()
    assert reasons, "the seeded taxonomy must be non-empty"
    return [r["id"] for r in reasons[:limit]]


# --- available_actions: the contract the UI renders ------------------------


async def test_available_actions_are_per_actor(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    cast = await _submitted_over_http(client, app_session, make_user)
    cid = cast["claim_id"]

    # The claimant can see their submitted claim but has nothing to do on it.
    detail = (await client.get(f"{BASE}/claims/{cid}")).json()
    assert detail["available_actions"] == []
    assert detail["row_version"] is not None  # the CAS token exists post-submit
    assert detail["status"] == "division_approval"

    await login(client, *cast["approver"][0:2], cast["approver"][2])
    approver_view = (await client.get(f"{BASE}/claims/{cid}")).json()
    assert set(approver_view["available_actions"]) == {"approve", "return"}


async def test_a_draft_offers_submit_and_cancel_to_its_owner(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """A draft has no workflow instance, so the engine cannot answer — the
    module synthesizes the pre-instance action set."""
    division = await make_org_unit(app_session, kind="division")
    staff = await make_staff(app_session, division_id=division.id)
    user, pw = await make_user(roles=("staff",), staff_id=staff.id)
    await app_session.commit()

    await login(client, user, pw)
    draft = (await client.post(f"{BASE}/claims", json={}, headers=CSRF)).json()
    assert draft["available_actions"] == ["submit", "cancel"]
    assert draft["row_version"] is None
    assert draft["sla_state"] is None


# --- approve: the whole chain ---------------------------------------------


async def test_approve_walks_the_chain_to_paid_closed(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """Every forward move is the SAME ``approve`` action — this is why one
    endpoint covers Approve, "hand to FMS" and "mark paid & close"."""
    cast = await _submitted_over_http(client, app_session, make_user)
    cid = cast["claim_id"]

    await login(client, *cast["approver"][0:2], cast["approver"][2])
    first = await client.post(
        f"{BASE}/claims/{cid}/approve", json={}, headers=CSRF
    )
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "admin_review"
    assert first.json()["next_action"] == "Final check & print packet"
    # The chief is done — the claim left their queue.
    assert first.json()["available_actions"] == []

    await login(client, *cast["admin"][0:2], cast["admin"][2])
    handed = await client.post(f"{BASE}/claims/{cid}/approve", json={}, headers=CSRF)
    assert handed.json()["status"] == "handed_to_fms"
    assert handed.json()["holder_kind"] == "external_fms"

    paid = await client.post(f"{BASE}/claims/{cid}/approve", json={}, headers=CSRF)
    assert paid.json()["status"] == "paid_closed"
    assert paid.json()["available_actions"] == []  # terminal
    assert paid.json()["holder_kind"] is None
    assert paid.json()["next_action"] is None


async def test_approve_bumps_the_cas_token(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    cast = await _submitted_over_http(client, app_session, make_user)
    cid = cast["claim_id"]
    await login(client, *cast["approver"][0:2], cast["approver"][2])
    before = (await client.get(f"{BASE}/claims/{cid}")).json()["row_version"]
    after = (
        await client.post(f"{BASE}/claims/{cid}/approve", json={}, headers=CSRF)
    ).json()["row_version"]
    assert after > before


async def test_stale_expected_version_409s(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """The screen moved under the approver — act on the fresh state, not the
    stale one (workflow-standards §4)."""
    cast = await _submitted_over_http(client, app_session, make_user)
    cid = cast["claim_id"]
    await login(client, *cast["approver"][0:2], cast["approver"][2])
    stale = (await client.get(f"{BASE}/claims/{cid}")).json()["row_version"] - 1

    resp = await client.post(
        f"{BASE}/claims/{cid}/approve",
        json={"expected_version": stale},
        headers=CSRF,
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["error"]["code"] == "stale_workflow_version"


async def test_a_bystander_cannot_approve(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    cast = await _submitted_over_http(client, app_session, make_user)
    cid = cast["claim_id"]
    outsider, outsider_pw = await make_user(roles=("staff",))
    await app_session.commit()

    await login(client, outsider, outsider_pw)
    resp = await client.post(f"{BASE}/claims/{cid}/approve", json={}, headers=CSRF)
    assert resp.status_code == 403, resp.text
    assert resp.json()["error"]["code"] == "workflow_not_authorized"


async def test_segregation_is_filtered_from_the_action_set_not_only_enforced(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """A chief who filed their own claim must not be OFFERED Approve. Before
    R-4-screens ``available_actions`` listed it and the POST 409'd — a button
    that is certain to fail (COA 92-389 four-eyes)."""
    office = await make_org_unit(app_session, kind="office")
    division = await make_org_unit(app_session, kind="division", parent=office)
    chief_staff = await make_staff(app_session, division_id=division.id)
    chief_secret = pyotp.random_base32()
    chief, chief_pw = await make_user(
        roles=("staff",), staff_id=chief_staff.id,
        mfa_enabled=True, mfa_secret=chief_secret,
    )
    await grant_scoped_role(
        app_session, user=chief, role_code="approver", org_unit_id=division.id
    )
    # A second approver so holder resolution can exclude the originator.
    other, _, _ = await _mfa_user(make_user)
    await grant_scoped_role(
        app_session, user=other, role_code="approver", org_unit_id=division.id
    )
    await ensure_reimb_workflow(app_session)
    await app_session.commit()

    await login(client, chief, chief_pw, chief_secret)
    cid = (await client.post(f"{BASE}/claims", json={}, headers=CSRF)).json()["id"]
    await client.patch(
        f"{BASE}/claims/{cid}",
        json={
            "purpose": "Own trip",
            "destination_region_code": "13",
            "date_depart": "2026-07-01",
            "date_return": "2026-07-03",
        },
        headers=CSRF,
    )
    await client.put(
        f"{BASE}/claims/{cid}/legs",
        json={
            "legs": [
                {"leg_date": "2026-07-01", "transport_mode": "bus", "fare": "500.00"}
            ]
        },
        headers=CSRF,
    )
    submitted = await client.post(f"{BASE}/claims/{cid}/submit", headers=CSRF)
    assert submitted.status_code == 200, submitted.text
    # Approve is withheld even though the chief holds the gate permission…
    assert "approve" not in submitted.json()["available_actions"]

    # …and forcing it still 409s: the filter is UX, the guard is the law.
    forced = await client.post(f"{BASE}/claims/{cid}/approve", json={}, headers=CSRF)
    assert forced.status_code == 409, forced.text
    assert forced.json()["error"]["code"] == "segregation_of_duties"


# --- return: ≥1 taxonomy reason -------------------------------------------


async def test_return_with_no_reasons_is_a_field_anchored_422(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """The wire schema rejects it with a ``body.reason_ids`` loc, so the FE's
    422→field mapper anchors the error on the reason picker itself."""
    cast = await _submitted_over_http(client, app_session, make_user)
    cid = cast["claim_id"]
    await login(client, *cast["approver"][0:2], cast["approver"][2])

    resp = await client.post(
        f"{BASE}/claims/{cid}/return",
        json={"comment": "Fix the fare.", "reason_ids": []},
        headers=CSRF,
    )
    assert resp.status_code == 422, resp.text
    body = resp.json()["error"]
    assert body["code"] == "validation_error"
    assert any("reason_ids" in detail["loc"] for detail in body["details"])


async def test_return_rejects_ids_outside_the_live_taxonomy(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    cast = await _submitted_over_http(client, app_session, make_user)
    cid = cast["claim_id"]
    await login(client, *cast["approver"][0:2], cast["approver"][2])

    resp = await client.post(
        f"{BASE}/claims/{cid}/return",
        json={"comment": "Fix the fare.", "reason_ids": [987654]},
        headers=CSRF,
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "reimb_unknown_return_reason"


async def test_return_requires_a_comment_too(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    cast = await _submitted_over_http(client, app_session, make_user)
    cid = cast["claim_id"]
    await login(client, *cast["approver"][0:2], cast["approver"][2])
    reasons = await _reason_ids(client)

    resp = await client.post(
        f"{BASE}/claims/{cid}/return",
        json={"comment": "", "reason_ids": reasons},
        headers=CSRF,
    )
    assert resp.status_code == 422, resp.text
    assert any(
        "comment" in detail["loc"] for detail in resp.json()["error"]["details"]
    )


async def test_return_lands_with_the_claimant_and_records_the_reasons(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    cast = await _submitted_over_http(client, app_session, make_user)
    cid = cast["claim_id"]
    await login(client, *cast["approver"][0:2], cast["approver"][2])
    reasons = await _reason_ids(client, limit=2)

    resp = await client.post(
        f"{BASE}/claims/{cid}/return",
        json={"comment": "Attach the official receipt.", "reason_ids": reasons},
        headers=CSRF,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "returned"
    assert resp.json()["next_action"] == "Fix and resubmit"

    event = (
        await app_session.execute(
            select(ReimbReturnEvent).where(ReimbReturnEvent.claim_id == cid)
        )
    ).scalar_one()
    assert event.reason_ids == reasons
    assert event.free_comment == "Attach the official receipt."
    assert event.step_id is not None

    # The ball is back with the claimant, who may now fix and resubmit.
    owner, owner_pw, _ = cast["owner"]
    await login(client, owner, owner_pw)
    owner_view = (await client.get(f"{BASE}/claims/{cid}")).json()
    assert set(owner_view["available_actions"]) == {"resubmit", "cancel"}


async def test_returned_claim_resubmits_and_re_enters_the_chain(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    cast = await _submitted_over_http(client, app_session, make_user)
    cid = cast["claim_id"]
    await login(client, *cast["approver"][0:2], cast["approver"][2])
    ref_before = (await client.get(f"{BASE}/claims/{cid}")).json()["ref_no"]
    await client.post(
        f"{BASE}/claims/{cid}/return",
        json={"comment": "Fix the fare.", "reason_ids": await _reason_ids(client)},
        headers=CSRF,
    )

    owner, owner_pw, _ = cast["owner"]
    await login(client, owner, owner_pw)
    resubmitted = await client.post(f"{BASE}/claims/{cid}/submit", headers=CSRF)
    assert resubmitted.status_code == 200, resubmitted.text
    body = resubmitted.json()
    assert body["status"] == "division_approval"
    assert body["ref_no"] == ref_before  # never a second RB number
    # Back in the approver's queue, and out of the claimant's hands.
    assert body["holder_kind"] == "user"
    assert body["holder_display"] == cast["approver"][0].email
    assert body["available_actions"] == []
