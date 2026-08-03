"""R-3 — the documentary-packet HTTP surface + the download holder authorizer.

What this pins:

- ``GET /checklist`` is a genuine read (no rows created by looking);
- multipart upload works end to end and answers with the whole packet, so the
  progress line and the row that changed refresh together;
- the packet is claim-scoped on BOTH sides: only the owner may write it, and the
  ``register_holder_authorizer`` seam scopes core's download route without a
  single change to core's router;
- (the flag-OFF → 404 contract for these routes lives with its siblings in
  ``test_reimb_api_flag_gate.py`` — one canonical home for the gate.)
"""

from __future__ import annotations

import pyotp
from sqlalchemy import select

from office_connect.core.models import Attachment
from tests.conftest import CSRF, login
from tests.reimb_checklist_helpers import satisfy_packet_over_http, tiny_jpeg
from tests.reimb_lifecycle_helpers import ensure_reimb_workflow
from tests.reimbursement_helpers import make_staff
from tests.workflow_helpers import grant_scoped_role, make_org_unit

BASE = "/api/v1/reimbursement"


async def _packet_cast(client, app_session, make_user):
    """An owner with a wizard-complete claim, plus a scoped approver and an
    unrelated bystander (both able to log in)."""
    office = await make_org_unit(app_session, kind="office")
    division = await make_org_unit(app_session, kind="division", parent=office)
    staff = await make_staff(app_session, division_id=division.id)
    owner, owner_pw = await make_user(roles=("staff",), staff_id=staff.id)

    secret = pyotp.random_base32()
    approver, approver_pw = await make_user(mfa_enabled=True, mfa_secret=secret)
    await grant_scoped_role(
        app_session, user=approver, role_code="approver", org_unit_id=division.id
    )

    other_staff = await make_staff(
        app_session, division_id=(await make_org_unit(app_session, kind="division")).id
    )
    bystander, bystander_pw = await make_user(
        roles=("staff",), staff_id=other_staff.id
    )

    await ensure_reimb_workflow(app_session)
    await app_session.commit()

    await login(client, owner, owner_pw)
    cid = (await client.post(f"{BASE}/claims", json={}, headers=CSRF)).json()["id"]
    await client.patch(
        f"{BASE}/claims/{cid}",
        json={
            "purpose": "Regional review",
            "destination": "Manila",
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
    return {
        "claim_id": cid,
        "owner": (owner, owner_pw),
        "approver": (approver, approver_pw, secret),
        "bystander": (bystander, bystander_pw),
    }


def _by_code(payload):
    return {item["code"]: item for item in payload["items"]}


# --- read -------------------------------------------------------------------


async def test_the_checklist_lists_the_applicable_items_without_creating_rows(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    from sqlalchemy import func

    from office_connect.modules.reimbursement.models import ReimbChecklistItem

    cast = await _packet_cast(client, app_session, make_user)
    before = (
        await app_session.execute(
            select(func.count()).select_from(ReimbChecklistItem)
        )
    ).scalar_one()

    resp = await client.get(f"{BASE}/claims/{cast['claim_id']}/checklist")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    items = _by_code(body)
    assert {"TO-01", "IOT-45", "CTC-47", "AR-01", "DV-32"} <= set(items)
    assert all(item["item_id"] is None for item in body["items"])
    assert items["TO-01"]["status"] == "missing"
    assert items["IOT-45"]["evidence"] == "generated_doc"

    # Only the two human-evidence items block; the generated ones never do.
    assert {b["code"] for b in body["summary"]["blocking"]} == {"TO-01", "CTC-47"}
    assert body["summary"] == {
        **body["summary"],
        "required_total": 2,
        "required_done": 0,
        "complete": False,
    }
    assert "TO-01" in body["summary"]["gate_message"]

    assert (
        await app_session.execute(
            select(func.count()).select_from(ReimbChecklistItem)
        )
    ).scalar_one() == before


async def test_the_checklist_is_not_bureau_public(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    cast = await _packet_cast(client, app_session, make_user)
    bystander, pw = cast["bystander"]
    await login(client, bystander, pw)
    resp = await client.get(f"{BASE}/claims/{cast['claim_id']}/checklist")
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "reimb_not_claim_owner"


# --- write ------------------------------------------------------------------


async def test_upload_answers_with_the_whole_packet(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    cast = await _packet_cast(client, app_session, make_user)
    cid = cast["claim_id"]
    catalog_id = _by_code(
        (await client.get(f"{BASE}/claims/{cid}/checklist")).json()
    )["TO-01"]["catalog_id"]

    resp = await client.post(
        f"{BASE}/claims/{cid}/checklist/{catalog_id}/attachments",
        files={"file": ("travel-order.jpg", tiny_jpeg(), "image/jpeg")},
        headers=CSRF,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    item = _by_code(body)["TO-01"]
    assert item["status"] == "attached"
    assert item["item_id"] is not None  # materialized on write, not on read
    assert len(item["files"]) == 1

    stored = item["files"][0]
    assert stored["filename"] == "travel-order.jpg"
    # A fresh upload is not yet servable, so no link is offered — the FE says
    # "checking" rather than dangling a URL that would 409.
    assert stored["scan_status"] == "pending"
    assert stored["download_path"] is None

    # The progress line moved in the SAME response as the row.
    assert body["summary"]["required_done"] == 1
    assert {b["code"] for b in body["summary"]["blocking"]} == {"CTC-47"}


async def test_a_disallowed_file_type_is_refused(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    cast = await _packet_cast(client, app_session, make_user)
    cid = cast["claim_id"]
    catalog_id = _by_code(
        (await client.get(f"{BASE}/claims/{cid}/checklist")).json()
    )["TO-01"]["catalog_id"]

    resp = await client.post(
        f"{BASE}/claims/{cid}/checklist/{catalog_id}/attachments",
        files={"file": ("evil.svg", b"<svg/>", "image/svg+xml")},
        headers=CSRF,
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "attachment_rejected"


async def test_only_the_owner_may_edit_the_packet(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    cast = await _packet_cast(client, app_session, make_user)
    cid = cast["claim_id"]
    catalog_id = _by_code(
        (await client.get(f"{BASE}/claims/{cid}/checklist")).json()
    )["TO-01"]["catalog_id"]

    bystander, pw = cast["bystander"]
    await login(client, bystander, pw)
    resp = await client.post(
        f"{BASE}/claims/{cid}/checklist/{catalog_id}/attachments",
        files={"file": ("x.jpg", tiny_jpeg(), "image/jpeg")},
        headers=CSRF,
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "reimb_not_claim_owner"


async def test_the_packet_locks_when_the_claim_leaves_the_claimant(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    cast = await _packet_cast(client, app_session, make_user)
    cid = cast["claim_id"]
    await satisfy_packet_over_http(client, cid)
    catalog_id = _by_code(
        (await client.get(f"{BASE}/claims/{cid}/checklist")).json()
    )["TO-01"]["catalog_id"]
    assert (
        await client.post(f"{BASE}/claims/{cid}/submit", headers=CSRF)
    ).status_code == 200

    resp = await client.post(
        f"{BASE}/claims/{cid}/checklist/{catalog_id}/attachments",
        files={"file": ("late.jpg", tiny_jpeg(), "image/jpeg")},
        headers=CSRF,
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "reimb_claim_not_editable"


async def test_detach_reopens_the_item_and_the_gate(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    cast = await _packet_cast(client, app_session, make_user)
    cid = cast["claim_id"]
    catalog_id = _by_code(
        (await client.get(f"{BASE}/claims/{cid}/checklist")).json()
    )["TO-01"]["catalog_id"]
    uploaded = await client.post(
        f"{BASE}/claims/{cid}/checklist/{catalog_id}/attachments",
        files={"file": ("to.jpg", tiny_jpeg(), "image/jpeg")},
        headers=CSRF,
    )
    join_id = _by_code(uploaded.json())["TO-01"]["files"][0]["id"]

    resp = await client.request(
        "DELETE",
        f"{BASE}/claims/{cid}/checklist/{catalog_id}/attachments/{join_id}",
        headers=CSRF,
    )
    assert resp.status_code == 200, resp.text
    item = _by_code(resp.json())["TO-01"]
    assert (item["status"], item["files"]) == ("missing", [])
    assert "TO-01" in {b["code"] for b in resp.json()["summary"]["blocking"]}


# --- the download seam ------------------------------------------------------


async def test_downloads_are_claim_scoped_by_the_registered_holder_authorizer(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """``core/attachments/authz.py`` promised at Stage B that wiring a module
    needs "zero router change" — this is that promise being collected."""
    cast = await _packet_cast(client, app_session, make_user)
    cid = cast["claim_id"]
    catalog_id = _by_code(
        (await client.get(f"{BASE}/claims/{cid}/checklist")).json()
    )["TO-01"]["catalog_id"]
    uploaded = await client.post(
        f"{BASE}/claims/{cid}/checklist/{catalog_id}/attachments",
        files={"file": ("to.jpg", tiny_jpeg(), "image/jpeg")},
        headers=CSRF,
    )
    attachment_id = _by_code(uploaded.json())["TO-01"]["files"][0]["attachment_id"]

    # Mark it clean so the fail-closed scan gate is not what we are measuring.
    row = (
        await app_session.execute(
            select(Attachment).where(Attachment.id == attachment_id)
        )
    ).scalar_one()
    row.scan_status = "clean"
    await app_session.commit()

    owner_read = await client.get(f"/api/v1/attachments/{attachment_id}/content")
    assert owner_read.status_code == 200
    assert owner_read.headers["X-Content-Type-Options"] == "nosniff"

    bystander, pw = cast["bystander"]
    await login(client, bystander, pw)
    denied = await client.get(f"/api/v1/attachments/{attachment_id}/content")
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "forbidden"

    approver, approver_pw, secret = cast["approver"]
    await login(client, approver, approver_pw, secret)
    scoped = await client.get(f"/api/v1/attachments/{attachment_id}/content")
    assert scoped.status_code == 200
