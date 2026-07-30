"""R-2-wizard — the module surface's feature-flag→404 gate + gate ordering.

The whole ``/api/v1/reimbursement`` router sits behind ``require_feature``:
flag OFF → 404 on every route, even authenticated (the module is
indistinguishable from absent — fail-safe). Ordering contracts pinned here:
CSRF middleware fires before routing (a header-less POST 403s even when the
flag is OFF), the flag gate fires before auth (OFF → 404 beats 401), and with
the flag ON the ordinary 401/403 gates take over.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from office_connect.core.models import FeatureFlag
from tests.conftest import CSRF, login


@pytest.fixture
async def reimb_flag_off(app_session):
    """Force ``module.reimbursement`` OFF for the test, restoring the prior
    state after (the dev DB may have been flipped ON by a walkthrough)."""
    row = (
        await app_session.execute(
            select(FeatureFlag).where(FeatureFlag.key == "module.reimbursement")
        )
    ).scalar_one_or_none()
    created = row is None
    prev = None if created else (row.enabled, row.is_active)
    if created:
        row = FeatureFlag(
            key="module.reimbursement",
            enabled=False,
            description="Local Travel Reimbursement module",
        )
        app_session.add(row)
    else:
        row.enabled = False
    await app_session.commit()
    yield row
    if not created:
        row.enabled, row.is_active = prev
        await app_session.commit()


async def test_flag_off_404s_the_whole_surface_even_authenticated(
    client, make_user, session_redis, seed_rbac, app_session, reimb_flag_off
):
    user, pw = await make_user(roles=("staff",))
    await login(client, user, pw)

    for method, path, kwargs in (
        ("GET", "/api/v1/reimbursement/my-work", {}),
        ("GET", "/api/v1/reimbursement/claims/1", {}),
        ("GET", "/api/v1/reimbursement/regions", {}),
        ("POST", "/api/v1/reimbursement/claims", {"json": {}, "headers": CSRF}),
    ):
        resp = await client.request(method, path, **kwargs)
        assert resp.status_code == 404, (method, path, resp.text)
        assert resp.json()["error"]["code"] == "not_found"


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
