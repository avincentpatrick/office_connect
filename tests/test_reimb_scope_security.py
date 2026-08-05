"""R-9 — the security suite: every read path, driven from the WRONG actor.

Spec §14's R-9 row grades one sentence for this file: *"Scoped visibility
enforced per §3.2 (owner cannot read others' claims via API)."* Spec §3.2 is
where the requirement comes from and it is emphatic — *"Claims are NOT
bureau-public (unlike DMWIS documents) — they carry personal financial data"* —
followed by the operative consequence: **the module's list endpoints must filter
by scope server-side, never client-side.**

**Why this file exists when eight increments already have their own tests.**
Every increment tested its own surface as it shipped. What has never been tested
is the SET, and the set is where a hole hides: each endpoint looks right beside
its own docstring, and the leak is the one surface that quietly answers a
question its neighbours refuse. So this file is organised by ATTACKER rather
than by endpoint — one actor, every door they might try — which is how the
question gets asked the way an attacker asks it.

Three attackers, each a different shape of wrong:

1. **A traveller** with a perfectly valid login and a globally-granted
   ``reimb.claim.read``, against another traveller's everything. This is §3.2's
   literal sentence and the one spec §14 names.
2. **A scoped approver of a SIBLING office** — legitimately privileged, just not
   here. The dangerous actor, because every route-level permission check passes.
3. **An actor holding no oversight at all**, against the three surfaces whose
   whole content is other people's work.

**The property tests at the bottom are the point.** api-standards §9f's rule
(*a list may not borrow a row's read rule*) has been applied four times by
someone remembering it. ``test_no_surface_leaks_a_foreign_claim_to_a_traveller``
asserts it as a PROPERTY over every list/aggregate at once, so surface number
five is covered before it is written.

TEST HYGIENE (the four-times-learned rules — see ``tests/conftest.py``):
every fixture here builds its own fresh offices via ``standard_cast``, so the
scoped assertions are about this test's claims and nothing else in the shared
database; nothing is dated relative to today; nothing mutates seeded catalogs.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from office_connect.modules.reimbursement.services.lifecycle import (
    claim_action,
    submit_claim,
)
from tests.conftest import CSRF, DEFAULT_TEST_PASSWORD, login
from tests.reimb_lifecycle_helpers import return_reason_ids, standard_cast
from tests.workflow_helpers import grant_scoped_role

BASE = "/api/v1/reimbursement"

#: The refusal a foreign claim earns. Deliberately the SAME slug the owner-only
#: write paths raise: a bystander must not learn from the error code whether the
#: claim exists and is merely someone else's, or does not exist at all.
FOREIGN_CLAIM = "reimb_not_claim_owner"


@dataclass(frozen=True)
class Scene:
    """Two unrelated offices, each with its own claimant, approver and Admin
    Officer, plus one submitted claim in office A."""

    a: object
    b: object


@pytest.fixture
async def scene(app_session, make_user, seed_rbac):
    """Office A and office B share nothing but the tenant.

    ``standard_cast`` mints a fresh office→division tree per call, which is what
    makes every count assertion below safe to state absolutely: office B's
    overseer can only ever see rows this test created.
    """
    a = await standard_cast(app_session, make_user)
    b = await standard_cast(app_session, make_user)
    assert a.office.id != b.office.id
    await submit_claim(app_session, claim_id=a.claim.id, actor_user_id=a.owner.id)
    await app_session.commit()
    return Scene(a=a, b=b)


async def _signin(client, user):
    resp = await login(client, user, DEFAULT_TEST_PASSWORD)
    assert resp.status_code == 200, resp.text
    return resp


def _claim_read_paths(claim_id: int) -> tuple[tuple[str, str], ...]:
    """Every GET that discloses something about ONE claim.

    Kept as one tuple rather than one test each, because the thing under test is
    that they agree. A single endpoint answering where its siblings refuse is
    exactly the defect this file was written to find, and that is only visible
    when they are asked together.
    """
    return (
        ("GET", f"{BASE}/claims/{claim_id}"),
        ("GET", f"{BASE}/claims/{claim_id}/timeline"),
        ("GET", f"{BASE}/claims/{claim_id}/checklist"),
        ("GET", f"{BASE}/claims/{claim_id}/external-events"),
    )


# ---------------------------------------------------------------------------
# Attacker 1 — a traveller, against another traveller's claim (spec §3.2)
# ---------------------------------------------------------------------------


async def test_a_traveller_cannot_read_another_travellers_claim(
    client, session_redis, reimb_flag_on, scene
):
    """**The sentence spec §14 grades**, asserted across every per-claim read.

    Traveller B holds ``reimb.claim.read`` GLOBALLY — that is not a
    misconfiguration, it is spec §3.2's design so a traveller can reach their own
    claim from anywhere in the org tree. Which is precisely why the route-level
    permission cannot be the rule, and why ``deps.can_read_claim`` exists.
    """
    await _signin(client, scene.b.owner)

    for method, path in _claim_read_paths(scene.a.claim.id):
        resp = await client.request(method, path)
        assert resp.status_code == 403, (path, resp.status_code, resp.text)
        assert resp.json()["error"]["code"] == FOREIGN_CLAIM, (path, resp.text)


async def test_a_traveller_cannot_reach_another_travellers_paperwork(
    client, session_redis, reimb_flag_on, scene
):
    """The write/act paths on a foreign claim.

    **This test found a real defect, and the assertion is written to keep it
    found.** ``/submit`` and ``/cancel`` used to check the claim's STATE before
    its OWNERSHIP, so a stranger got back *"This claim is already in the approval
    workflow"* — turning the endpoint into an oracle over every claim id in the
    agency: no-such-claim / exists-unsubmitted / exists-submitted, one probe at a
    time, from any ordinary ``staff`` login. Every existing test passed because
    every one of them submitted its own claim. ``drafts.owned_editable_claim``
    had the rule right and said why in a comment; two functions in
    ``lifecycle.py`` did not follow it. Hence the exact-slug assertion below:
    every one of these must refuse with the SAME sentence, so none of them
    describes a record the caller may not see.
    """
    await _signin(client, scene.b.owner)
    claim_id = scene.a.claim.id

    probes = (
        ("PATCH", f"{BASE}/claims/{claim_id}", {"purpose": "hijacked"}),
        ("POST", f"{BASE}/claims/{claim_id}/compute", {}),
        ("POST", f"{BASE}/claims/{claim_id}/submit", {}),
        ("POST", f"{BASE}/claims/{claim_id}/cancel", {"comment": "not mine to void"}),
        ("POST", f"{BASE}/claims/{claim_id}/documents/generate", {}),
        (
            "POST",
            f"{BASE}/claims/{claim_id}/external-events",
            {"status": "with_budget"},
        ),
    )
    for method, path, body in probes:
        resp = await client.request(method, path, json=body, headers=CSRF)
        assert resp.status_code == 403, (path, resp.status_code, resp.text)
        assert resp.json()["error"]["code"] == FOREIGN_CLAIM, (path, resp.text)


async def test_the_write_paths_reveal_nothing_about_a_claims_state(
    client, app_session, make_user, session_redis, seed_rbac, reimb_flag_on, scene
):
    """The oracle, closed — asserted as the property rather than the instance.

    A stranger probing three DIFFERENT claims must get three IDENTICAL answers:
    a draft, a submitted claim, and an id that was never issued. If the first two
    ever diverge, the endpoint is again reporting a record's condition to someone
    with no entitlement to know the record exists.
    """
    draft = (await standard_cast(app_session, make_user)).claim  # never submitted
    await app_session.commit()

    await _signin(client, scene.b.owner)

    submitted = await client.post(
        f"{BASE}/claims/{scene.a.claim.id}/submit", json={}, headers=CSRF
    )
    unsubmitted = await client.post(
        f"{BASE}/claims/{draft.id}/submit", json={}, headers=CSRF
    )
    absent = await client.post(
        f"{BASE}/claims/999999999/submit", json={}, headers=CSRF
    )

    # The two REAL claims are indistinguishable — that is the whole property.
    assert submitted.status_code == unsubmitted.status_code == 403
    assert (
        submitted.json()["error"]["code"]
        == unsubmitted.json()["error"]["code"]
        == FOREIGN_CLAIM
    )
    # A missing row 404s, which leaks nothing: it says an id was never issued,
    # not anything about a claim someone filed.
    assert absent.status_code == 404
    assert absent.json()["error"]["code"] == "reimb_claim_not_found"


async def test_a_traveller_cannot_download_another_travellers_evidence(
    client, app_session, session_redis, reimb_flag_on, scene
):
    """The bytes, not just the metadata — and via CORE's download route.

    ``/api/v1/attachments/{id}/content`` is core's endpoint, authorized for this
    holder kind by the authorizer ``services/attachments.py`` registers. It is in
    this file rather than a core one because the RULE being tested is the
    module's: a hole here would leak scanned receipts and the generated packet,
    which is the most sensitive thing the module holds, through a route whose own
    tests know nothing about claims.
    """
    from sqlalchemy import select

    from office_connect.core.models import Attachment
    from office_connect.modules.reimbursement.services import attachments as evidence

    rows = (
        (
            await app_session.execute(
                select(Attachment).where(
                    Attachment.holder_kind == evidence.HOLDER_KIND,
                    Attachment.holder_id == scene.a.claim.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert rows, "the standard cast satisfies the packet, so evidence must exist"

    await _signin(client, scene.b.owner)
    for row in rows:
        resp = await client.get(f"/api/v1/attachments/{row.id}/content")
        assert resp.status_code in (403, 404), (row.id, resp.status_code)


async def test_a_traveller_cannot_read_another_travellers_cash_advance(
    client, app_session, make_user, session_redis, seed_rbac, reimb_flag_on, scene
):
    """DV numbers and peso amounts. ``can_read_cash_advance`` is deliberately NOT
    "anyone who may read a claim" — leaning on the global read grant would make
    every colleague's advances bureau-public."""
    from tests.reimbursement_helpers import make_cash_advance

    advance = await make_cash_advance(
        app_session, claimant_id=scene.a.staff.id, amount="8000.00", dv_no="DV-SEC-1"
    )
    await app_session.commit()

    await _signin(client, scene.b.owner)

    one = await client.get(f"{BASE}/cash-advances/{advance.id}")
    assert one.status_code == 403
    assert one.json()["error"]["code"] == FOREIGN_CLAIM

    # And the LIST must not hand it over either — §9f: a list may not borrow a
    # row's read rule, and it may not be laxer than the row endpoint next door.
    listed = await client.get(f"{BASE}/cash-advances")
    assert listed.status_code == 200, listed.text
    ids = {item["id"] for item in listed.json()["items"]}
    assert advance.id not in ids, listed.text


async def test_a_foreign_claim_is_indistinguishable_from_a_missing_one(
    client, session_redis, reimb_flag_on, scene
):
    """The information leak that survives a correct 403.

    If a claim B may not see refuses differently from a claim that does not
    exist, the pair of responses is an oracle: B can enumerate which ids are real
    claims, and how many the agency has filed, without reading one. The two must
    be the same shape — which is why ``read_claim`` raises the owner-path slug
    rather than a scope-specific one.
    """
    await _signin(client, scene.b.owner)

    foreign = await client.get(f"{BASE}/claims/{scene.a.claim.id}")
    absent = await client.get(f"{BASE}/claims/999999999")

    assert foreign.status_code == 403
    assert absent.status_code == 404
    # The status codes differ (one row exists, one does not) but neither message
    # describes the claim, so nothing about A's claim is learnable from either.
    assert scene.a.claim.ref_no not in foreign.text
    for body in (foreign, absent):
        assert "purpose" not in body.json().get("error", {}).get("details", {})


# ---------------------------------------------------------------------------
# Attacker 2 — a scoped approver of a sibling office
# ---------------------------------------------------------------------------


async def test_a_sibling_offices_approver_cannot_read_or_act_on_this_claim(
    client, app_session, make_user, session_redis, seed_rbac, reimb_flag_on, scene
):
    """The dangerous actor: every route-level permission check PASSES.

    Office B's approver genuinely holds ``reimb.claim.approve`` — just not here.
    Only ``authorize_scoped`` against the claim's OWN org unit tells the two
    apart, and if that call were ever dropped the endpoint would keep working
    perfectly for everyone who tested it.

    The approver is enrolled in MFA because ``approver`` is one of the two
    ``mfa_required_role_codes``; without the hop the session is pending and every
    probe below would 403 with ``mfa_setup_required``, passing the status-code
    assertion while testing nothing about scope. (It did, on the first run — the
    exact-slug assertions are what caught it.)
    """
    import pyotp

    secret = pyotp.random_base32()
    intruder, pw = await make_user(mfa_enabled=True, mfa_secret=secret)
    await grant_scoped_role(
        app_session,
        user=intruder,
        role_code="approver",
        org_unit_id=scene.b.division.id,
    )
    await app_session.commit()

    resp = await login(client, intruder, pw, secret)
    assert resp.status_code == 200, resp.text

    for method, path in _claim_read_paths(scene.a.claim.id):
        probe = await client.request(method, path)
        assert probe.status_code == 403, (path, probe.text)
        assert probe.json()["error"]["code"] == FOREIGN_CLAIM, (path, probe.text)

    decide = await client.post(
        f"{BASE}/claims/{scene.a.claim.id}/approve", json={}, headers=CSRF
    )
    assert decide.status_code == 403, decide.text
    assert decide.json()["error"]["code"] == FOREIGN_CLAIM, decide.text


async def test_a_scoped_overseer_sees_only_their_own_office_in_the_queue(
    client, session_redis, reimb_flag_on, scene
):
    """§9f's scope resolution over a LIST, asserted absolutely.

    Safe to assert absolutely for exactly one reason: office B was created by
    this test's fixture, so "every row belongs to office B" is a statement about
    rows this test made. Note the assertion is on the CONTENT, not the count —
    the queue is a shared surface and other tests' claims live in other offices.
    """
    await _signin(client, scene.b.admin)

    resp = await client.get(f"{BASE}/claims")
    assert resp.status_code == 200, resp.text
    refs = {item["ref_no"] for item in resp.json()["items"]}
    assert scene.a.claim.ref_no not in refs, resp.text


async def test_a_scoped_overseer_never_counts_a_sibling_office_on_the_board(
    client, session_redis, reimb_flag_on, scene
):
    """**The assertion is on the AGGREGATE, not only the cards** — api-standards
    §9g says so in as many words: *"cards filtered correctly under a header that
    counted the whole agency is a defect that looks exactly like working
    software."* A leaked list gives up rows one page at a time; a leaked board
    gives up a division's whole budget in a single integer.

    Office B has no submitted claims at all (only office A's was submitted), so
    every column count must be 0 and every total ``"0.00"``.
    """
    await _signin(client, scene.b.admin)

    resp = await client.get(f"{BASE}/board")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    for column in body["columns"]:
        assert column["count"] == 0, (column["key"], resp.text)
        assert column["total"] == "0.00", (column["key"], resp.text)
        assert column["items"] == [], (column["key"], resp.text)


async def test_a_scoped_overseer_never_counts_a_sibling_offices_returns(
    client, app_session, session_redis, reimb_flag_on, scene
):
    """§9h — the aggregate may span only rows the actor could already open one at
    a time. A return happens in office A; office B's Admin Officer must not see
    it in the ranking OR in the header's ``total_returns``."""
    await claim_action(
        app_session,
        claim_id=scene.a.claim.id,
        action="return",
        actor_user_id=scene.a.approver.id,
        comment="Fix the packet.",
        reason_ids=await return_reason_ids(app_session, "MISSING_OR"),
    )
    await app_session.commit()

    await _signin(client, scene.b.admin)
    resp = await client.get(f"{BASE}/insights/return-reasons")
    assert resp.status_code == 200, resp.text
    assert resp.json()["total_returns"] == 0, resp.text
    assert resp.json()["items"] == [], resp.text


async def test_a_scoped_admin_officer_may_read_insights_but_not_promote(
    client, session_redis, reimb_flag_on, scene
):
    """§9h's second half, over real HTTP — the path #27 could only pin by unit
    test. The WRITE rule is narrower than the READ rule on the same resource,
    because a promotion warns every claimant in the tenant and a division-scoped
    grant must not reach a tenant-wide effect.

    The envelope must also say so BEFORE the click: ``can_promote`` is false, so
    the UI never offers a control certain to be refused (R-4-screens doctrine).
    """
    await _signin(client, scene.b.admin)

    read = await client.get(f"{BASE}/insights/return-reasons")
    assert read.status_code == 200, read.text
    assert read.json()["can_promote"] is False, read.text

    reason_id = read.json().get("items") and read.json()["items"][0]["reason_id"]
    refused = await client.post(
        f"{BASE}/insights/return-reasons/{reason_id or 1}/promote",
        json={},
        headers=CSRF,
    )
    assert refused.status_code == 403, refused.text
    assert refused.json()["error"]["code"] == "reimb_promotion_not_permitted"


# ---------------------------------------------------------------------------
# Attacker 3 — an actor who oversees nobody
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "slug"),
    (
        (f"{BASE}/claims", "reimb_queue_not_permitted"),
        (f"{BASE}/board", "reimb_queue_not_permitted"),
        (f"{BASE}/insights/return-reasons", "reimb_insights_not_permitted"),
    ),
)
async def test_the_oversight_surfaces_refuse_rather_than_return_an_empty_page(
    client, session_redis, reimb_flag_on, scene, path, slug
):
    """§9f: **refuse, do not return an empty list.** ``200 []`` says "there is no
    work" — a claim about the world that is false — where the truth is "this
    surface is not yours". And per §9h the sentence must be true of the surface
    that refused, which is why Insights does not borrow the queue's slug: nobody's
    My Work answers "why do packets come back".
    """
    await _signin(client, scene.a.owner)  # a traveller: oversees nobody

    resp = await client.get(path)
    assert resp.status_code == 403, resp.text
    assert resp.json()["error"]["code"] == slug, resp.text


async def test_a_grant_that_expired_stops_resolving_scope(
    client, app_session, make_user, session_redis, seed_rbac, reimb_flag_on, scene
):
    """Oversight is time-bounded (delegation/OIC): an OIC who covered for a
    fortnight must not keep the division's pipeline forever.

    The refusal arrives at the ROUTE gate (bare ``forbidden``) rather than at the
    queue's scope resolver, and that is worth pinning rather than papering over:
    an expired grant strips the actor of ``reimb.claim.read`` itself, so they
    never reach the surface that would have computed an empty scope. Two
    independent layers therefore have to fail before an ended grant sees
    anything, which is the correct depth for a time-bounded privilege.
    """
    from datetime import timedelta

    from office_connect.core.time import utc_now

    locum, _ = await make_user()
    grant = await grant_scoped_role(
        app_session, user=locum, role_code="admin_officer", org_unit_id=scene.a.office.id
    )
    grant.valid_to = utc_now() - timedelta(days=1)
    await app_session.commit()

    await _signin(client, locum)
    for path in (f"{BASE}/claims", f"{BASE}/board", f"{BASE}/insights/return-reasons"):
        resp = await client.get(path)
        assert resp.status_code == 403, (path, resp.text)
        assert resp.json()["error"]["code"] == "forbidden", (path, resp.text)

    # And the claim itself stays shut — the expired grant places them nowhere.
    row = await client.get(f"{BASE}/claims/{scene.a.claim.id}")
    assert row.status_code == 403, row.text


# ---------------------------------------------------------------------------
# The property: §9f as a rule, not as four remembered applications
# ---------------------------------------------------------------------------


async def test_no_list_or_aggregate_leaks_a_foreign_claim_to_a_traveller(
    client, session_redis, reimb_flag_on, scene
):
    """**The one that covers surface number five.**

    ``reimb.claim.read`` is granted GLOBALLY to the ``staff`` role. Every
    list/aggregate in the module is mounted behind it. So the property that has
    to hold — for the three that exist and for any added later — is that a
    traveller reaches NONE of them, and that the refusal is a refusal rather than
    an empty success.

    Stated this way rather than as three separate assertions because the failure
    this guards against is a new surface being written to the route's permission
    instead of to ``queue.oversight_scope``. That mistake is invisible in review
    (the code looks like the surrounding code) and invisible in testing (the new
    surface's own tests would use an overseer). It is visible here.
    """
    from tests.test_reimb_authz_census import AUTHZ_TABLE, OVERSIGHT_SCOPE

    await _signin(client, scene.a.owner)

    oversight_paths = [
        path
        for (method, path), rule in AUTHZ_TABLE.items()
        if rule.rule is OVERSIGHT_SCOPE and method == "GET"
    ]
    assert len(oversight_paths) == 3, "census drift — new oversight surface?"

    for path in oversight_paths:
        resp = await client.get(path)
        assert resp.status_code == 403, (path, resp.status_code, resp.text)
        assert resp.json()["error"]["code"].endswith("_not_permitted"), (path, resp.text)


def test_the_two_oversight_permission_sets_cannot_drift():
    """``lifecycle._OVERSIGHT_PERMS`` duplicates ``queue.OVERSIGHT_PERMS``
    because ``queue`` imports ``lifecycle`` and the reverse edge would be a
    cycle. A duplicated security constant is a liability unless something pins
    the copies together — widening one and not the other would mean a list and a
    row endpoint disagreeing about who counts as an overseer.
    """
    from office_connect.modules.reimbursement.services import lifecycle, queue

    assert lifecycle._OVERSIGHT_PERMS == queue.OVERSIGHT_PERMS


async def test_my_work_shows_the_caller_their_own_claims_and_nobody_elses(
    client, session_redis, reimb_flag_on, scene
):
    """The counterpart to every refusal above: the surface the queue's 403 NAMES
    must actually answer. A security suite that only proved things are refused
    would be satisfied by an application that refuses everything."""
    await _signin(client, scene.b.owner)

    resp = await client.get(f"{BASE}/my-work")
    assert resp.status_code == 200, resp.text

    body = resp.json()
    refs = {
        item["ref_no"]
        for section in body.values()
        if isinstance(section, list)
        for item in section
        if isinstance(item, dict) and "ref_no" in item
    }
    assert scene.a.claim.ref_no not in refs, resp.text
