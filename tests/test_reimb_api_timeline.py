"""R-4-screens — the claim tracker feed + the return-reason taxonomy endpoint.

The tracker is the claimant's answer to "where is my money?" (spec §9.2), so
the two things pinned hardest here are ordering and *attribution*: a return's
reasons must ride the row that return produced, and never a neighbouring one.
Reasons reach the claimant verbatim (spec §12).
"""

from __future__ import annotations

from tests.conftest import CSRF, login
from tests.test_reimb_api_actions import BASE, _reason_ids, _submitted_over_http


async def test_return_reasons_lists_the_live_taxonomy(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    division_user = await _submitted_over_http(client, app_session, make_user)
    del division_user  # the cast only exists to seed + authenticate

    reasons = (await client.get(f"{BASE}/return-reasons")).json()
    codes = [r["code"] for r in reasons]
    assert "MISSING_OR" in codes
    assert "PER_DIEM_CALC" in codes
    assert all({"id", "code", "label", "category"} <= set(r) for r in reasons)

    # The catalog has no `sort` column, so the order is `category, code` — and
    # because `category` is a PG ENUM, Postgres sorts it by DECLARATION order,
    # not alphabetically. That happens to be the authored taxonomy order
    # (missing_doc first, other last), which is exactly the chip order an
    # approver wants. Pinned so a future enum edit is a visible decision.
    assert [r["category"] for r in reasons] == [
        "missing_doc",
        "wrong_amount",
        "wrong_form",
        "no_signature",
        "late",
        "policy",
        "other",
    ]
    assert codes[0] == "MISSING_OR"
    assert codes[-1] == "OTHER"


async def test_timeline_tracks_the_journey_and_attaches_return_reasons(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    cast = await _submitted_over_http(client, app_session, make_user)
    cid = cast["claim_id"]

    await login(client, *cast["approver"][0:2], cast["approver"][2])
    reasons = await _reason_ids(client, limit=2)
    returned = await client.post(
        f"{BASE}/claims/{cid}/return",
        json={"comment": "Attach the official receipt.", "reason_ids": reasons},
        headers=CSRF,
    )
    assert returned.status_code == 200, returned.text

    owner, owner_pw, _ = cast["owner"]
    await login(client, owner, owner_pw)
    timeline = (await client.get(f"{BASE}/claims/{cid}/timeline")).json()

    moves = [(e["from_status"], e["to_status"]) for e in timeline]
    assert moves == [
        (None, "draft"),
        ("draft", "division_approval"),
        ("division_approval", "returned"),
    ]
    assert timeline[1]["to_status_label"] == "For Approval"
    assert timeline[-1]["from_status_label"] == "For Approval"

    # Reasons ride ONLY the row the return produced.
    assert timeline[0]["reasons"] == []
    assert timeline[1]["reasons"] == []
    bounce = timeline[-1]
    assert [r["id"] for r in bounce["reasons"]] == reasons
    assert bounce["note"] == "Attach the official receipt."  # verbatim, spec §12
    assert bounce["actor_display"] == cast["approver"][0].email


async def test_timeline_is_not_bureau_public(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """Same read rule as the claim itself (spec §3.2) — and the same slug, so a
    bystander cannot tell "not yours" from "does not exist"."""
    cast = await _submitted_over_http(client, app_session, make_user)
    outsider, outsider_pw = await make_user(roles=("staff",))
    await app_session.commit()

    await login(client, outsider, outsider_pw)
    resp = await client.get(f"{BASE}/claims/{cast['claim_id']}/timeline")
    assert resp.status_code == 403, resp.text
    assert resp.json()["error"]["code"] == "reimb_not_claim_owner"


async def test_a_fresh_draft_already_has_a_tracker_row(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    from tests.reimbursement_helpers import make_staff
    from tests.workflow_helpers import make_org_unit

    division = await make_org_unit(app_session, kind="division")
    staff = await make_staff(app_session, division_id=division.id)
    user, pw = await make_user(roles=("staff",), staff_id=staff.id)
    await app_session.commit()

    await login(client, user, pw)
    cid = (await client.post(f"{BASE}/claims", json={}, headers=CSRF)).json()["id"]

    timeline = (await client.get(f"{BASE}/claims/{cid}/timeline")).json()
    assert len(timeline) == 1
    assert timeline[0]["from_status"] is None
    assert timeline[0]["to_status"] == "draft"
    assert timeline[0]["from_status_label"] is None
    assert timeline[0]["to_status_label"] == "Draft"
