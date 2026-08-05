"""R-9 — the authorization CENSUS: every route declares a rule, or the suite fails.

Spec §14's R-9 row carries its own exclamation mark — *"Security suite (scope
filters!)"* — and this file is why. api-standards §9f's rule (**a list may not
borrow a row's read rule**) has now been applied four separate times: the queue
(§9f), the board (§9g), Insights (§9h) and §9h's narrower agency-wide WRITE
rule. Every one of those four was applied because a person remembered to. The
question this file answers is whether a FIFTH surface would get it right by
default, and the only honest answer is one that does not depend on memory.

**So the test enumerates rather than lists.** ``tests/test_reimb_api_flag_gate.py``
used to carry a hand-written tuple of paths to probe, and a hand-written list has
exactly one failure mode: a route added tomorrow is simply *absent* from it, and
absence never fails a test. Here the routes come out of the running app, and
:data:`AUTHZ_TABLE` must account for every one of them. Add a route without a
row and this module fails with the path in the message.

**What a row asserts, and what it deliberately does not.** A row records the
route's *declared* wiring — the feature-gate class and the route-level
permission, both read off the app through the ``oc_feature_flag`` /
``oc_permission`` markers ``core/auth/dependencies.py`` attaches — plus the name
of the EXACT rule the service applies underneath. The first two are machine-
checked here. The third is a cross-reference, not an assertion: proving that
``GET /claims`` really is scoped on oversight is what
``test_reimb_scope_security.py`` does with two actors and real data. This file
proves the map is COMPLETE; that file proves the territory matches it.

**The one thing the table makes impossible to miss.** Read the ``permission``
column: all but four routes are gated on ``reimb.claim.read`` / ``.create`` /
``.submit`` — the three permissions the ``staff`` role carries *globally*, so a
traveller can reach their own claim from anywhere in the org tree. That is §9f's
warning as data rather than as prose: on 28 of 32 routes the route-level gate
cannot possibly be the scope rule, because an ordinary user passes it. The
``rule`` column is where the actual answer lives, every time.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from fastapi.routing import APIRoute

from office_connect.modules.reimbursement.workflow import FEATURE_FLAG_KEY
from tests.conftest import CSRF, login

PREFIX = "/api/v1/reimbursement"

# --- gate classes -----------------------------------------------------------

#: Behind ``require_feature(module.reimbursement)`` — flag OFF → 404 before auth,
#: so an OFF module is indistinguishable from an absent one (api-standards §9).
GATED = "gated"

#: Mounted on the SEPARATE un-gated actions router. The flag blocks NEW work but
#: must never strand work already in the chain (workflow-standards §9, §9a).
#: A route may only be here if refusing it would trap an in-flight instance.
UNGATED_ACTION = "ungated_action"

# --- rule classes: the EXACT rule, applied in the service beneath the route ---

#: ``deps.can_read_claim`` — the claimant, or an actor whose review/approve/
#: fms_update grant covers the claim's org unit.
OWNER_OR_SCOPED = "owner_or_scoped"

#: ``drafts.owned_editable_claim`` — the claimant alone, and only while the claim
#: is still editable. No scoped actor reaches these.
OWNER_ONLY = "owner_only"

#: ``drafts.owned_editable_claim`` OR ``deps.has_scoped_grant`` — the two doors
#: onto generation (api-standards §9d).
OWNER_OR_SCOPED_ACTOR = "owner_or_scoped_actor"

#: ``deps.has_scoped_grant`` — a scoped actor only; ownership deliberately does
#: NOT qualify (relaying what FMS said is not the traveller's to assert).
SCOPED_ACTOR = "scoped_actor"

#: ``queue.oversight_scope`` — §9f. Keyed on the OVERSIGHT permission set, never
#: on the route's globally-granted ``reimb.claim.read``. No oversight → 403,
#: never ``200 []``.
OVERSIGHT_SCOPE = "oversight_scope"

#: ``insights.may_promote`` — §9h. An AGENCY-WIDE grant, because the write's
#: effect is tenant-wide. Narrower than the read rule on the same resource.
AGENCY_WIDE_WRITE = "agency_wide_write"

#: ``deps.can_read_cash_advance`` — owner or a scoped manager/reviewer.
#: Deliberately not "anyone who may read a claim": DV numbers and peso amounts.
CA_OWNER_OR_SCOPED = "ca_owner_or_scoped"

#: ``deps.can_manage_cash_advances`` — a scoped ``reimb.cash_advance.manage``
#: holder. The one place the route-level permission is already the narrow one.
CA_SCOPED_MANAGER = "ca_scoped_manager"

#: The workflow engine's own step authorizer decides — the actor must hold the
#: transition's ``required_permission`` for the instance's org unit AND be a
#: live holder of the step (workflow-standards §3).
ENGINE_STEP_HOLDER = "engine_step_holder"

#: Reference/taxonomy data, readable by any authenticated holder of the route's
#: permission. Explicitly listed rather than merely unscoped — that is the point
#: of the census: "this one has no scope rule" must be a DECISION on the record,
#: not a gap nobody noticed. Neither row carries per-claimant data.
REFERENCE_ANY_HOLDER = "reference_any_holder"

#: My Work is scoped by CONSTRUCTION, not by a check: the query is keyed on the
#: caller's own ``staff_id``, so there is no foreign row for a rule to exclude.
SELF_BY_CONSTRUCTION = "self_by_construction"


@dataclass(frozen=True)
class Rule:
    gate: str
    permission: str
    rule: str
    #: Why, where the answer is not obvious from the columns.
    note: str = ""


#: Every route under ``/api/v1/reimbursement``. Keyed ``(METHOD, path)`` exactly
#: as FastAPI registers it. **A new route needs a row here or the suite fails.**
AUTHZ_TABLE: dict[tuple[str, str], Rule] = {
    # --- the claimant's own claim ------------------------------------------
    ("POST", f"{PREFIX}/claims"): Rule(
        GATED, "reimb.claim.create", OWNER_ONLY,
        "Creates for the CALLER's own staff row — the body cannot name a claimant.",
    ),
    ("GET", f"{PREFIX}/claims/{{claim_id}}"): Rule(
        GATED, "reimb.claim.read", OWNER_OR_SCOPED,
        "Spec §3.2: claims are NOT bureau-public. The route permission is global "
        "on `staff`, so `can_read_claim` is the whole rule.",
    ),
    ("PATCH", f"{PREFIX}/claims/{{claim_id}}"): Rule(
        GATED, "reimb.claim.create", OWNER_ONLY,
    ),
    ("PUT", f"{PREFIX}/claims/{{claim_id}}/legs"): Rule(
        GATED, "reimb.claim.create", OWNER_ONLY,
    ),
    ("POST", f"{PREFIX}/claims/{{claim_id}}/compute"): Rule(
        GATED, "reimb.claim.create", OWNER_ONLY,
    ),
    ("POST", f"{PREFIX}/claims/{{claim_id}}/submit"): Rule(
        GATED, "reimb.claim.submit", OWNER_ONLY,
        "Both branches (first submit and resubmit) re-check under the row lock.",
    ),
    ("POST", f"{PREFIX}/claims/{{claim_id}}/cancel"): Rule(
        GATED, "reimb.claim.create", OWNER_ONLY,
        "Owner while Draft only (spec §6.1 row 9); post-submit voiding is a "
        "workflow transition, not this route.",
    ),
    ("POST", f"{PREFIX}/claims/{{claim_id}}/spawn-reimbursement"): Rule(
        GATED, "reimb.claim.create", OWNER_ONLY,
    ),
    # --- documentary packet -------------------------------------------------
    ("GET", f"{PREFIX}/claims/{{claim_id}}/checklist"): Rule(
        GATED, "reimb.claim.read", OWNER_OR_SCOPED,
    ),
    (
        "POST",
        f"{PREFIX}/claims/{{claim_id}}/checklist/{{catalog_id}}/attachments",
    ): Rule(GATED, "reimb.claim.create", OWNER_ONLY),
    (
        "DELETE",
        f"{PREFIX}/claims/{{claim_id}}/checklist/{{catalog_id}}"
        f"/attachments/{{attachment_id}}",
    ): Rule(GATED, "reimb.claim.create", OWNER_ONLY),
    ("POST", f"{PREFIX}/claims/{{claim_id}}/documents/generate"): Rule(
        GATED, "reimb.claim.read", OWNER_OR_SCOPED_ACTOR,
        "§9d's two doors. NOT widened to `can_read_claim`: a global read grant "
        "would let any employee enqueue renders on any claim they can see.",
    ),
    # --- cash advances (§9e) -------------------------------------------------
    ("POST", f"{PREFIX}/cash-advances"): Rule(
        GATED, "reimb.cash_advance.manage", CA_SCOPED_MANAGER,
    ),
    ("GET", f"{PREFIX}/cash-advances"): Rule(
        GATED, "reimb.claim.read", CA_OWNER_OR_SCOPED,
        "A LIST on a globally-granted permission — §9f applies; the service "
        "filters to the caller's own advances unless they manage/review.",
    ),
    ("GET", f"{PREFIX}/cash-advances/{{cash_advance_id}}"): Rule(
        GATED, "reimb.claim.read", CA_OWNER_OR_SCOPED,
    ),
    ("PATCH", f"{PREFIX}/cash-advances/{{cash_advance_id}}"): Rule(
        GATED, "reimb.cash_advance.manage", CA_SCOPED_MANAGER,
    ),
    ("POST", f"{PREFIX}/cash-advances/{{cash_advance_id}}/liquidate"): Rule(
        GATED, "reimb.claim.create", OWNER_ONLY,
        "Starting a liquidation is the traveller's own act — the advance is "
        "theirs. Recording one FOR them is the Admin Officer's PATCH above.",
    ),
    # --- FMS relay (R-7-events) ---------------------------------------------
    ("POST", f"{PREFIX}/claims/{{claim_id}}/external-events"): Rule(
        GATED, "reimb.claim.read", SCOPED_ACTOR,
        "Ownership does NOT qualify: a traveller may not assert what FMS said "
        "about their own claim.",
    ),
    ("GET", f"{PREFIX}/claims/{{claim_id}}/external-events"): Rule(
        GATED, "reimb.claim.read", OWNER_OR_SCOPED,
        "Asymmetric with the POST above on purpose — reading where your packet "
        "got to is exactly what a claimant should be able to do.",
    ),
    # --- the oversight surfaces (§9f / §9g / §9h) ---------------------------
    ("GET", f"{PREFIX}/claims"): Rule(
        GATED, "reimb.claim.read", OVERSIGHT_SCOPE,
        "§9f, instance 1. The route permission is held globally by every "
        "traveller; the queue is keyed on the OVERSIGHT set instead.",
    ),
    ("GET", f"{PREFIX}/board"): Rule(
        GATED, "reimb.claim.read", OVERSIGHT_SCOPE,
        "§9g. Its own segment, not `/claims/board` — `/claims/{claim_id}` is "
        "registered first and would swallow the literal.",
    ),
    ("GET", f"{PREFIX}/insights/return-reasons"): Rule(
        GATED, "reimb.claim.read", OVERSIGHT_SCOPE,
        "§9h — the scope IS the privacy boundary; the aggregate may span only "
        "rows the actor could already open one at a time.",
    ),
    ("POST", f"{PREFIX}/insights/return-reasons/{{reason_id}}/promote"): Rule(
        GATED, "reimb.claim.review", AGENCY_WIDE_WRITE,
        "§9h — the WRITE rule is narrower than the READ rule on the same "
        "resource, because a promotion warns every claimant in the tenant.",
    ),
    ("POST", f"{PREFIX}/insights/return-reasons/{{reason_id}}/demote"): Rule(
        GATED, "reimb.claim.review", AGENCY_WIDE_WRITE,
    ),
    # --- the traveller's own surfaces + reference data ----------------------
    ("GET", f"{PREFIX}/my-work"): Rule(
        GATED, "reimb.claim.read", SELF_BY_CONSTRUCTION,
        "The surface the queue's 403 names as the one that DOES answer a "
        "traveller's question.",
    ),
    ("GET", f"{PREFIX}/claims/{{claim_id}}/timeline"): Rule(
        GATED, "reimb.claim.read", OWNER_OR_SCOPED,
    ),
    ("GET", f"{PREFIX}/regions"): Rule(
        GATED, "reimb.claim.read", REFERENCE_ANY_HOLDER,
        "PSGC regions + EO 77 clusters. Public regulation, no claimant data.",
    ),
    ("GET", f"{PREFIX}/return-reasons"): Rule(
        GATED, "reimb.claim.read", REFERENCE_ANY_HOLDER,
        "The taxonomy + its `promoted` flags. Carries the wizard's advisory — "
        "the REASON, never a count and never a person (§9h).",
    ),
    # --- un-gated decision endpoints (§9a) ----------------------------------
    ("POST", f"{PREFIX}/claims/{{claim_id}}/approve"): Rule(
        UNGATED_ACTION, "reimb.claim.read", ENGINE_STEP_HOLDER,
    ),
    ("POST", f"{PREFIX}/claims/{{claim_id}}/return"): Rule(
        UNGATED_ACTION, "reimb.claim.read", ENGINE_STEP_HOLDER,
        "Also enforces ≥1 taxonomy reason — the substrate R-8's whole loop "
        "reads back.",
    ),
    ("POST", f"{PREFIX}/claims/{{claim_id}}/mark-paid"): Rule(
        UNGATED_ACTION, "reimb.claim.read", SCOPED_ACTOR,
        "Records the payout THEN drives the transition (workflow-standards "
        "§12). Un-gated: a flag-OFF must not strand a claim FMS already paid.",
    ),
    ("POST", f"{PREFIX}/claims/{{claim_id}}/settle"): Rule(
        UNGATED_ACTION, "reimb.claim.read", CA_SCOPED_MANAGER,
        "Settlement is the Admin Officer's act, so it rides the cash-advance "
        "manage grant rather than the approval chain.",
    ),
}


# --- introspection ----------------------------------------------------------


def _observed() -> dict[tuple[str, str], tuple[list[str], list[str]]]:
    """``{(METHOD, path): (permissions, feature_flags)}`` read off the live app.

    The markers come from ``core/auth/dependencies.py``; a closure is otherwise
    opaque, and grepping the source would re-introduce exactly the hand-list
    problem this file exists to remove.
    """
    from office_connect.main import app

    found: dict[tuple[str, str], tuple[list[str], list[str]]] = {}
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith(PREFIX):
            continue
        perms, flags = [], []
        for dep in route.dependant.dependencies:
            perm = getattr(dep.call, "oc_permission", None)
            flag = getattr(dep.call, "oc_feature_flag", None)
            if perm is not None:
                perms.append(perm)
            if flag is not None:
                flags.append(flag)
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            found[(method, route.path)] = (perms, flags)
    return found


def _concrete(path: str) -> str:
    """A probe-able URL: every ``{param}`` becomes ``1``. Nothing with id 1 need
    exist — every assertion here is about the gate, which fires first."""
    out = []
    for segment in path.split("/"):
        out.append("1" if segment.startswith("{") and segment.endswith("}") else segment)
    return "/".join(out)


#: Bodies good enough to reach the gate. They never need to VALIDATE: FastAPI
#: solves a route's dependencies before its body, so the 404/403 under test
#: always precedes the 422 these would otherwise earn.
_PROBE_BODY: dict[str, dict] = {
    f"{PREFIX}/claims/1/return": {"comment": "x", "reason_ids": [1]},
    f"{PREFIX}/claims/1/mark-paid": {"payout_ref": "ADA-1", "paid_on": "2026-07-06"},
    f"{PREFIX}/claims/1/cancel": {"reason": "x"},
}


async def _probe(client, method: str, path: str):
    url = _concrete(path)
    if method == "GET":
        return await client.get(url)
    return await client.request(
        method, url, json=_PROBE_BODY.get(url, {}), headers=CSRF
    )


# --- the census itself ------------------------------------------------------


def test_every_route_declares_an_authorization_rule():
    """A route added with no scope rule FAILS this suite rather than merely
    being missed by it — the whole point of R-9 (spec §14's "scope filters!")."""
    undeclared = sorted(set(_observed()) - set(AUTHZ_TABLE))
    assert not undeclared, (
        "These routes are mounted under /api/v1/reimbursement with no row in "
        f"AUTHZ_TABLE: {undeclared}\n"
        "Add one. Before you do, answer api-standards §9f's question out loud: "
        "if the route's permission is one an ordinary traveller holds so they "
        "can see their OWN data, it cannot also decide WHOSE data they see. A "
        "list/aggregate belongs on OVERSIGHT_SCOPE; a tenant-wide write belongs "
        "on AGENCY_WIDE_WRITE (§9h)."
    )


def test_the_table_carries_no_stale_rows():
    """The inverse guard: a deleted route must not leave a row behind claiming
    a rule is enforced somewhere that no longer answers."""
    stale = sorted(set(AUTHZ_TABLE) - set(_observed()))
    assert not stale, f"AUTHZ_TABLE rows for routes that no longer exist: {stale}"


def test_the_census_matches_the_route_count():
    """A blunt backstop for the two set-comparisons above: if a refactor ever
    made ``_observed`` return nothing, both would pass vacuously."""
    assert len(_observed()) == 32


def test_each_route_declares_the_permission_the_app_actually_enforces():
    """The table's ``permission`` column is machine-checked, not decorative —
    silently widening a route's gate breaks this before it reaches review."""
    mismatched = {
        key: (declared.permission, perms)
        for key, (perms, _) in _observed().items()
        if (declared := AUTHZ_TABLE.get(key)) is not None
        and perms != [declared.permission]
    }
    assert not mismatched, f"route permission drift (declared, actual): {mismatched}"


def test_the_gate_class_matches_how_the_route_is_mounted():
    """§9a's exemption is a deliberate, narrow list. Mounting a new route on the
    un-gated actions router is a security decision, so it must be spelled
    ``UNGATED_ACTION`` in the table before the app agrees with it."""
    for key, (_, flags) in _observed().items():
        declared = AUTHZ_TABLE[key]
        if declared.gate == GATED:
            assert flags == [FEATURE_FLAG_KEY], (
                f"{key} is declared GATED but the app mounts it behind {flags}"
            )
        else:
            assert flags == [], (
                f"{key} is declared UNGATED_ACTION but sits behind {flags}"
            )


def test_only_in_flight_decisions_are_exempt_from_the_flag():
    """workflow-standards §9: the flag blocks NEW work and must never strand
    work already in the chain. That is the ONLY justification for the exemption,
    so pin the membership — a fifth un-gated route is a decision, not a detail."""
    ungated = {
        path for (_, path), rule in AUTHZ_TABLE.items()
        if rule.gate == UNGATED_ACTION
    }
    assert ungated == {
        f"{PREFIX}/claims/{{claim_id}}/approve",
        f"{PREFIX}/claims/{{claim_id}}/return",
        f"{PREFIX}/claims/{{claim_id}}/mark-paid",
        f"{PREFIX}/claims/{{claim_id}}/settle",
    }


def test_the_oversight_surfaces_are_never_keyed_on_a_globally_granted_permission():
    """§9f as an executable rule rather than a remembered one.

    ``reimb.claim.read`` is held GLOBALLY by the ``staff`` role. Any surface
    answering "which records may this actor see" must therefore resolve scope
    from the OVERSIGHT set — never from the route's permission. This asserts the
    property over the table, so it covers surfaces that do not exist yet.
    """
    for key, rule in AUTHZ_TABLE.items():
        if rule.rule is OVERSIGHT_SCOPE:
            assert rule.permission == "reimb.claim.read", key
    # And the converse: every list/aggregate over OTHER people's claims must
    # carry one of the two scope-resolving rules, never a bare read.
    for key in (
        ("GET", f"{PREFIX}/claims"),
        ("GET", f"{PREFIX}/board"),
        ("GET", f"{PREFIX}/insights/return-reasons"),
    ):
        assert AUTHZ_TABLE[key].rule is OVERSIGHT_SCOPE, key


# --- the flag gate, over HTTP, driven from the census -----------------------


@pytest.mark.parametrize(
    ("method", "path"),
    sorted(k for k, v in AUTHZ_TABLE.items() if v.gate == GATED),
)
async def test_flag_off_404s_every_gated_route(
    client, session_redis, reimb_flag_off, method, path
):
    """Replaces the hand-maintained probe list this file was written to retire.
    Flag OFF → 404 on every gated route, before auth: an OFF module is
    indistinguishable from an absent one (api-standards §9)."""
    resp = await _probe(client, method, path)
    assert resp.status_code == 404, (method, path, resp.text)
    assert resp.json()["error"]["code"] == "not_found", resp.text


@pytest.mark.parametrize(
    ("method", "path"),
    sorted(k for k, v in AUTHZ_TABLE.items() if v.gate == UNGATED_ACTION),
)
async def test_flag_off_never_strands_an_in_flight_decision(
    client, session_redis, reimb_flag_off, method, path
):
    """The exemption's actual contract: with the module switched OFF these still
    ANSWER. What they answer (401/403/404-on-claim/409) is the ordinary business
    of auth and the engine; only "the route is gone" is forbidden."""
    resp = await _probe(client, method, path)
    assert resp.json()["error"]["code"] != "not_found", (method, path, resp.text)


# --- the pilot cohort: no grants, no module ---------------------------------


@pytest.mark.parametrize(("method", "path"), sorted(AUTHZ_TABLE))
async def test_an_actor_with_no_reimb_grants_is_refused_on_every_route(
    client, make_user, session_redis, seed_rbac, reimb_flag_on, method, path
):
    """**The pilot cohort, asserted.** R-9's confirmed posture is that the flag
    answers "is this module on" and RBAC grants answer "for whom" — there is no
    default-role path anywhere in the codebase, so a user reaches the module
    only because an admin granted them a role. This is that claim under test,
    across all 32 routes at once: an authenticated user holding NO ``reimb.*``
    permission is refused everywhere, with the flag fully ON.

    A regression here would not look like a bug. It would look like the pilot
    quietly becoming the whole agency.
    """
    user, pw = await make_user()  # authenticated, zero roles
    await login(client, user, pw)
    resp = await _probe(client, method, path)
    assert resp.status_code == 403, (method, path, resp.text)
    assert resp.json()["error"]["code"] == "forbidden", resp.text
