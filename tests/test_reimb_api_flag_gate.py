"""R-2-wizard — the module surface's feature-flag→404 gate + gate ORDERING.

The ``/api/v1/reimbursement`` router sits behind ``require_feature``: flag OFF →
404 on every route, even authenticated (the module is indistinguishable from
absent — fail-safe). Ordering contracts pinned here: CSRF middleware fires
before routing (a header-less POST 403s even when the flag is OFF), the flag
gate fires before auth (OFF → 404 beats 401), and with the flag ON the ordinary
401/403 gates take over.

R-4-screens added the ONE exemption: the approver's decision endpoints are
mounted on a separate, un-gated router. The flag blocks NEW work; it must never
strand work already in the chain (workflow-standards §9 — ``execute_action``
never reads the flag).

**R-9 moved the COVERAGE half of this file into
``tests/test_reimb_authz_census.py``.** What lived here was a hand-maintained
tuple of paths to probe, and a hand-maintained list has exactly one failure
mode: a route added tomorrow is simply absent from it, and absence never fails.
The census enumerates ``app.routes`` instead and probes every gated route
flag-OFF, so that guarantee now grows by itself. This file keeps what the census
cannot express — the ORDER the gates fire in, which is about middleware and
dependency resolution rather than about any particular route.
"""

from __future__ import annotations

from tests.conftest import CSRF, login


async def test_flag_off_beats_401_for_anonymous_probes(
    client, session_redis, reimb_flag_off
):
    resp = await client.get("/api/v1/reimbursement/my-work")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


async def test_csrf_middleware_precedes_the_flag_gate(
    client, session_redis, reimb_flag_off
):
    """A header-less POST 403s before any routing/IO — even with the flag OFF
    (documented interplay: the CSRF wall is outermost, api-standards §6)."""
    resp = await client.post("/api/v1/reimbursement/claims", json={})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "csrf_failed"


async def test_flag_on_anonymous_is_401(client, session_redis, reimb_flag_on):
    resp = await client.get("/api/v1/reimbursement/my-work")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


async def test_flag_on_roleless_user_is_403(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_on
):
    user, pw = await make_user()  # no roles → no reimb.* permissions
    await login(client, user, pw)

    read = await client.get("/api/v1/reimbursement/my-work")
    assert read.status_code == 403
    assert read.json()["error"]["code"] == "forbidden"

    create = await client.post(
        "/api/v1/reimbursement/claims", json={}, headers=CSRF
    )
    assert create.status_code == 403
    assert create.json()["error"]["code"] == "forbidden"


# --- R-4-screens: the action endpoints are NOT behind the gate --------------


async def test_flag_off_does_not_strand_in_flight_approvals(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_off
):
    """The whole point of the exemption: with the module switched OFF, an
    approver's decision endpoints still ANSWER. They must not 404 — a 404 here
    would strand every claim mid-chain the moment someone flips the flag
    (workflow-standards §9). What they answer (401/403/404-on-claim/409) is the
    ordinary business of auth and the engine; only "the route is gone" is
    forbidden."""
    user, pw = await make_user(roles=("staff",))
    await login(client, user, pw)

    approve = await client.post(
        "/api/v1/reimbursement/claims/1/approve", json={}, headers=CSRF
    )
    returned = await client.post(
        "/api/v1/reimbursement/claims/1/return",
        json={"comment": "x", "reason_ids": [1]},
        headers=CSRF,
    )
    # R-7-events: closing a paid claim is a decision on an instance already in
    # the chain, so it takes the exemption too. Gated, a flag-OFF would strand
    # every claim at `handed_to_fms` with FMS having already paid it.
    paid = await client.post(
        "/api/v1/reimbursement/claims/1/mark-paid",
        json={"payout_ref": "ADA-1", "paid_on": "2026-07-06"},
        headers=CSRF,
    )
    for resp in (approve, returned, paid):
        assert resp.json()["error"]["code"] != "not_found", resp.text
        # A nonexistent claim id 404s as `reimb_claim_not_found`, never as the
        # flag gate's bare `not_found` — the distinction IS the contract.
        if resp.status_code == 404:
            assert resp.json()["error"]["code"] == "reimb_claim_not_found"


async def test_the_action_endpoints_still_answer_to_anonymous_probes_with_401(
    client, session_redis, reimb_flag_off
):
    """Un-gated is not un-authenticated: without the flag's 404 in front, the
    ordinary auth wall is what an anonymous caller hits."""
    resp = await client.post(
        "/api/v1/reimbursement/claims/1/approve", json={}, headers=CSRF
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


async def test_csrf_still_precedes_the_un_gated_action_routes(
    client, session_redis, reimb_flag_off
):
    resp = await client.post("/api/v1/reimbursement/claims/1/approve", json={})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "csrf_failed"


async def test_the_flag_gates_every_cash_advance_route(
    client, session_redis, make_user, reimb_flag_off
):
    """R-6-clock: recording a cash advance is NEW work, so it sits on the GATED
    router — flag OFF → 404 on all four routes, authenticated or not.

    Deliberately unlike the approve/return pair above: that exemption exists so
    the flag can never refuse a decision on an instance already in the chain
    (workflow-standards §9). Starting a 30-day clock is not finishing one.
    """
    user, pw = await make_user(roles=("admin_officer",))
    await login(client, user, pw)

    probes = (
        ("get", "/api/v1/reimbursement/cash-advances", None),
        ("get", "/api/v1/reimbursement/cash-advances/1", None),
        ("post", "/api/v1/reimbursement/cash-advances", {}),
        ("patch", "/api/v1/reimbursement/cash-advances/1", {}),
    )
    for method, path, body in probes:
        call = getattr(client, method)
        resp = (
            await call(path, json=body, headers=CSRF)
            if body is not None
            else await call(path, headers=CSRF)
        )
        assert resp.status_code == 404, f"{method} {path} → {resp.status_code}"
        assert resp.json()["error"]["code"] == "not_found", resp.text
