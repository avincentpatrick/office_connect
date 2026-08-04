"""R-5-packet — the combined packet on the wire, and who may ask for one.

Spec §9.2 promises the approver a "packet PDF preview". Three things have to be
true for that promise to be keepable, and each is pinned here:

- the packet rides ``ClaimDetail`` (not a sibling endpoint), so the buttons and
  the document they decide on can never arrive in two responses that disagree;
- its bytes are servable **inline** through the existing core route, scoped by
  the claim's own read rule — an embedded frame is impossible otherwise;
- an approver whose worker was down at submit can ask for one, because
  ``NEXT_ACTION[admin_review]`` tells them to print a packet and a screen that
  says that with no packet and no button is a dead end (§9.1 principle 4).
"""

from __future__ import annotations

from sqlalchemy import select

from office_connect.modules.reimbursement.documents import (
    PACKET,
    generate_claim_documents,
)
from office_connect.modules.reimbursement.models import ReimbClaim
from tests.conftest import CSRF, login
from tests.reimb_checklist_helpers import satisfy_packet_over_http
from tests.test_reimb_checklist_api import _packet_cast

BASE = "/api/v1/reimbursement"


class _FakeRenderer:
    name = "fake"

    def render(self, html: str, *, stylesheet: str) -> bytes:
        return b"%PDF-1.7\n" + str(len(html)).encode() + b"\n"


async def _computed(client, cid: int) -> None:
    """Money first — the generator refuses a claim with no totals snapshot."""
    resp = await client.post(f"{BASE}/claims/{cid}/compute", headers=CSRF)
    assert resp.status_code == 200, resp.text


async def _generate(app_session, cid: int, actor_user_id: int) -> None:
    """Stand in for the Celery worker, which no test process runs."""
    claim = (
        await app_session.execute(select(ReimbClaim).where(ReimbClaim.id == cid))
    ).scalar_one()
    results = await generate_claim_documents(
        app_session,
        claim_id=claim.id,
        actor_user_id=actor_user_id,
        renderer=_FakeRenderer(),
    )
    assert {r.outcome for r in results} == {"generated"}, [
        (r.document_key, r.detail) for r in results
    ]
    await app_session.commit()


# --- the preview ------------------------------------------------------------


async def test_claim_detail_carries_no_packet_until_one_is_generated(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """``null`` is a real state, not an error: a fresh draft simply has none.

    The UI must render an honest notice for it rather than an empty frame,
    which is why the field is nullable rather than absent.
    """
    cast = await _packet_cast(client, app_session, make_user)
    body = (await client.get(f"{BASE}/claims/{cast['claim_id']}")).json()
    assert body["packet"] is None


async def test_the_packet_rides_claim_detail_and_serves_inline(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    cast = await _packet_cast(client, app_session, make_user)
    cid = cast["claim_id"]
    owner, _pw = cast["owner"]
    await _computed(client, cid)
    await _generate(app_session, cid, owner.id)

    body = (await client.get(f"{BASE}/claims/{cid}")).json()
    packet = body["packet"]
    assert packet is not None
    # Pre-submit it is a DRAFT copy: no reference number has been allocated, so
    # the PDF carries the watermark and the card must say so.
    assert packet["is_draft"] is True
    assert body["ref_no"] is None
    assert len(packet["content_sha256"]) == 64
    assert len(packet["source_fingerprint"]) == 64

    # No new download route — core's, scoped by the holder authorizer, and
    # served `inline` because the bytes are ours (api-standards §9c). That last
    # header is the entire reason an <iframe> can display it.
    content = await client.get(packet["download_path"])
    assert content.status_code == 200, content.text
    assert content.headers["Content-Disposition"].startswith("inline")
    assert content.headers["X-Content-Type-Options"] == "nosniff"
    assert content.content.startswith(b"%PDF-")


async def test_the_approver_sees_the_packet_and_a_bystander_sees_nothing(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """One URL, three audiences (delta row 58). What differs is authorization,
    not the shape of the response."""
    cast = await _packet_cast(client, app_session, make_user)
    cid = cast["claim_id"]
    owner, _pw = cast["owner"]
    await _computed(client, cid)
    await satisfy_packet_over_http(client, cid)
    assert (
        await client.post(f"{BASE}/claims/{cid}/submit", headers=CSRF)
    ).status_code == 200
    await _generate(app_session, cid, owner.id)

    approver, approver_pw, secret = cast["approver"]
    await login(client, approver, approver_pw, secret)
    body = (await client.get(f"{BASE}/claims/{cid}")).json()
    packet = body["packet"]
    assert packet is not None
    # Post-submit it is the FILED copy — the reference number is on the page.
    assert packet["is_draft"] is False
    assert (await client.get(packet["download_path"])).status_code == 200

    bystander, bystander_pw = cast["bystander"]
    await login(client, bystander, bystander_pw)
    assert (await client.get(f"{BASE}/claims/{cid}")).status_code == 403
    assert (await client.get(packet["download_path"])).status_code == 403


async def test_a_voided_packet_is_not_offered(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """Editing the claim voids the packet, and a voided copy must vanish from
    the preview immediately — the whole point of voiding is that the document no
    longer describes the claim."""
    cast = await _packet_cast(client, app_session, make_user)
    cid = cast["claim_id"]
    owner, _pw = cast["owner"]
    await _computed(client, cid)
    await _generate(app_session, cid, owner.id)
    assert (await client.get(f"{BASE}/claims/{cid}")).json()["packet"] is not None

    resp = await client.patch(
        f"{BASE}/claims/{cid}", json={"purpose": "A corrected purpose"}, headers=CSRF
    )
    assert resp.status_code == 200, resp.text
    # The PATCH response itself already reports the packet as gone: the record
    # and its document refresh in one response, never two.
    assert resp.json()["packet"] is None
    assert (await client.get(f"{BASE}/claims/{cid}")).json()["packet"] is None


# --- who may ask for a packet ----------------------------------------------


async def test_the_owner_may_ask_while_the_claim_is_editable(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    cast = await _packet_cast(client, app_session, make_user)
    cid = cast["claim_id"]
    await _computed(client, cid)

    resp = await client.post(f"{BASE}/claims/{cid}/documents/generate", headers=CSRF)
    # 202 with `queued`, never 200 with documents — WeasyPrint never runs in a
    # request path, so this handler cannot have the finished PDFs to return.
    assert resp.status_code == 202, resp.text
    assert isinstance(resp.json()["queued"], bool)
    assert "checklist" in resp.json()


async def test_a_worker_down_degrades_non_blockingly(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """Spec §19.12, deterministically.

    With no enqueuer registered the request must still answer 202 with
    ``queued: false`` — never a 500 and never a refused save. That boolean is
    what lets the UI show an honest notice instead of a spinner that never
    resolves, and it is why the endpoint is safe to press again.
    """
    from office_connect.core.documents import queue as documents_queue

    cast = await _packet_cast(client, app_session, make_user)
    cid = cast["claim_id"]
    await _computed(client, cid)

    previous = documents_queue._enqueuer
    documents_queue.register_enqueuer(None)
    try:
        resp = await client.post(
            f"{BASE}/claims/{cid}/documents/generate", headers=CSRF
        )
    finally:
        documents_queue.register_enqueuer(previous)

    assert resp.status_code == 202, resp.text
    assert resp.json()["queued"] is False
    # The claim is untouched and still submittable — generation never gates it.
    assert (await client.get(f"{BASE}/claims/{cid}")).status_code == 200


async def test_a_scoped_approver_may_ask_after_submit(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """The second door (R-5-packet).

    ``NEXT_ACTION[admin_review]`` reads "Final check & print packet". If the
    render worker was down at submit, the approver arrives at that instruction
    with nothing to print — so they must be able to ask. ``owned_editable_claim``
    can never serve them: the claim is past editing and is not theirs.
    """
    cast = await _packet_cast(client, app_session, make_user)
    cid = cast["claim_id"]
    await _computed(client, cid)
    await satisfy_packet_over_http(client, cid)
    assert (
        await client.post(f"{BASE}/claims/{cid}/submit", headers=CSRF)
    ).status_code == 200

    # Even the OWNER is refused now — the claim has left their hands.
    refused = await client.post(
        f"{BASE}/claims/{cid}/documents/generate", headers=CSRF
    )
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "reimb_claim_not_editable"

    approver, approver_pw, secret = cast["approver"]
    await login(client, approver, approver_pw, secret)
    resp = await client.post(f"{BASE}/claims/{cid}/documents/generate", headers=CSRF)
    assert resp.status_code == 202, resp.text


async def test_a_bystander_may_not_ask(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """Not widened to "anyone who may read the claim": the ``staff`` role's read
    grant is GLOBAL (§3.2), so that would let any user in the bureau enqueue
    renders on every claim they can see."""
    cast = await _packet_cast(client, app_session, make_user)
    cid = cast["claim_id"]
    await _computed(client, cid)

    bystander, pw = cast["bystander"]
    await login(client, bystander, pw)
    resp = await client.post(f"{BASE}/claims/{cid}/documents/generate", headers=CSRF)
    assert resp.status_code == 403
    # The OWNER path's error, deliberately: a bystander must not learn from the
    # message whether the claim exists and is merely uneditable.
    assert resp.json()["error"]["code"] == "reimb_not_claim_owner"


async def test_the_packet_never_appears_in_the_checklist(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    """It satisfies no COA code, so the Documents task list must not show it —
    a claimant offered a "Remove" button on the system's own packet would be a
    requirement nobody wrote."""
    cast = await _packet_cast(client, app_session, make_user)
    cid = cast["claim_id"]
    owner, _pw = cast["owner"]
    await _computed(client, cid)
    await _generate(app_session, cid, owner.id)

    body = (await client.get(f"{BASE}/claims/{cid}/checklist")).json()
    every_file = [file for item in body["items"] for file in item["files"]]
    packet_id = (
        await client.get(f"{BASE}/claims/{cid}")
    ).json()["packet"]["attachment_id"]
    assert packet_id not in {f["attachment_id"] for f in every_file}
    assert PACKET not in {item["code"] for item in body["items"]}
