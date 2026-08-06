"""Stage D-1: `/auth/me` carries the caller's effective permissions.

The subject here is the **payload**, not the gate — `test_rbac_enforcement.py`
already proves the gate. What this file pins is api-standards §9j: a response
whose content is the caller's own authorization state, read through the SAME
resolver the gate reads, so a UI's picture of what it may open cannot drift from
what the server will actually allow.

The landing shell (`web/src/pages/HomePage.tsx`) renders entirely from this
field, so every case below has a visible consequence on a real screen.
"""

from sqlalchemy import select

from office_connect.core.models import Role
from office_connect.core.rbac import grant_role, revoke_role
from office_connect.core.seeds.rbac import ROLE_GRANTS
from tests.conftest import CSRF, login


async def _role_id(session, code):
    return (
        await session.execute(select(Role).where(Role.code == code))
    ).scalar_one().id


async def _me(client):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_me_carries_the_callers_effective_permissions(
    client, make_user, session_redis, seed_rbac
):
    user, pw = await make_user(roles=("staff",))
    await login(client, user, pw)

    body = await _me(client)

    # Exactly the seeded staff grant — not a superset, not the catalog.
    assert body["permissions"] == sorted(ROLE_GRANTS["staff"])


async def test_me_permissions_are_sorted_on_a_miss_and_on_a_hit(
    client, make_user, session_redis, seed_rbac
):
    """`PermissionCache.get_or_load` returns a `set` on BOTH paths, so an
    unsorted response would be non-deterministic as a function of cache warmth —
    stable on a warm dev box, arbitrary in production (api-standards §9j)."""
    user, pw = await make_user(roles=("admin_officer",))
    await login(client, user, pw)

    first = (await _me(client))["permissions"]  # cold: the loader path
    second = (await _me(client))["permissions"]  # warm: the Redis path

    assert first == sorted(first)
    assert second == sorted(second)
    assert first == second


async def test_a_grant_less_user_gets_an_empty_list_not_an_error(
    client, make_user, session_redis, seed_rbac
):
    """After R-9 this is the COMMON case, not the edge one: nothing in the
    codebase auto-assigns a role (api-standards §9i), so a user reaches a module
    only because an administrator granted them one. `[]` is the wire value the
    landing's no-access state is built on — it must arrive as data, not as an
    error the client has to interpret."""
    user, pw = await make_user()
    await login(client, user, pw)

    body = await _me(client)

    assert body["permissions"] == []
    assert body["roles"] == []


async def test_a_grant_lands_on_the_next_me_request_while_roles_stay_stale(
    client,
    make_user,
    session_redis,
    session_store,
    permission_cache,
    app_session,
    seed_rbac,
):
    """The single most valuable assertion in this file.

    It is the fact that justifies the whole re-gate (ui-standards §7): `roles`
    is stamped into the session at login and `set_permissions_version` never
    rewrites it, so a nav gated on roles stayed WRONG until the user signed in
    again. `permissions` is read through the version-keyed cache and is correct
    on the very next request — no re-login.
    """
    target, pw = await make_user(roles=("staff",))
    admin, _ = await make_user(roles=("system_admin",))
    await login(client, target, pw)

    before = await _me(client)
    assert "audit.read" not in before["permissions"]
    assert before["roles"] == ["staff"]

    await grant_role(
        app_session,
        session_store,
        permission_cache,
        target_user_id=target.id,
        role_id=await _role_id(app_session, "auditor"),
        actor_id=admin.id,
    )

    after = await _me(client)
    # The permission set is fresh...
    assert "audit.read" in after["permissions"]
    # ...and `roles` is provably NOT. Same session, same request.
    assert after["roles"] == ["staff"]


async def test_a_revoke_lands_on_the_next_me_request(
    client,
    make_user,
    session_redis,
    session_store,
    permission_cache,
    app_session,
    seed_rbac,
):
    target, pw = await make_user(roles=("staff",))
    admin, _ = await make_user(roles=("system_admin",))
    grant = await grant_role(
        app_session,
        session_store,
        permission_cache,
        target_user_id=target.id,
        role_id=await _role_id(app_session, "auditor"),
        actor_id=admin.id,
    )
    await login(client, target, pw)
    assert "audit.read" in (await _me(client))["permissions"]

    await revoke_role(
        app_session,
        session_store,
        permission_cache,
        target_user_id=target.id,
        grant_id=grant.id,
        actor_id=admin.id,
    )

    assert "audit.read" not in (await _me(client))["permissions"]


async def test_me_answers_with_real_permissions_while_a_password_change_is_pending(
    client, make_user, session_redis, seed_rbac
):
    """`/auth/me` is reachable under `require_session_pending_ok`, and the field
    is deliberately NOT special-cased there. Returning `[]` for a pending session
    would tell a freshly-bootstrapped administrator — whose first login is always
    pending — that they have no access at all."""
    user, pw = await make_user(roles=("staff",), must_change_password=True)
    await login(client, user, pw)

    body = await _me(client)

    assert body["must_change_password"] is True
    assert body["permissions"] == sorted(ROLE_GRANTS["staff"])


async def test_me_answers_on_a_cold_permission_cache(
    client, make_user, session_redis, seed_rbac
):
    """The loader path reached from `/auth/me` rather than from a gated route —
    the branch most easily missed, because every pre-existing test warms the
    cache through `require_permission` first."""
    user, pw = await make_user(roles=("approver",))
    await login(client, user, pw)

    for key in await session_redis.keys(f"authz:perm:{user.id}:*"):
        await session_redis.delete(key)

    assert (await _me(client))["permissions"] == sorted(ROLE_GRANTS["approver"])


async def test_the_me_surface_and_the_gate_agree(
    client, make_user, session_redis, seed_rbac
):
    """The "never offer a button the server refuses" invariant, asserted.

    One resolver serves both (`effective_permission_codes`), so a claim in the
    payload and the gate's verdict on the same permission cannot disagree. If
    this test ever fails, a UI somewhere is showing a destination that 403s.
    """
    auditor, auditor_pw = await make_user(roles=("auditor",))
    await login(client, auditor, auditor_pw)
    assert "rbac.role.read" in (await _me(client))["permissions"]
    assert (await client.get("/api/v1/rbac/roles")).status_code == 200

    staff, staff_pw = await make_user(roles=("staff",))
    await client.post("/api/v1/auth/logout", headers=CSRF)
    await login(client, staff, staff_pw)
    assert "rbac.role.read" not in (await _me(client))["permissions"]
    assert (await client.get("/api/v1/rbac/roles")).status_code == 403


def test_the_oversight_triple_is_what_the_nav_mirrors():
    """`web/src/app/nav.ts` gates Claim queue / Pipeline board / Insights on
    exactly these three codes, because holding ANY of them is equivalent to
    `queue.oversight_scope()` returning a non-empty scope (api-standards §9f).

    If this fails, the server's oversight set moved and the FRONTEND is now
    lying about who can open those surfaces. Update `NAV_GROUPS`'
    `requiredPermissions` (and its census row) in the same commit.
    """
    from office_connect.modules.reimbursement.services.queue import OVERSIGHT_PERMS

    assert OVERSIGHT_PERMS == (
        "reimb.claim.review",
        "reimb.claim.fms_update",
        "reimb.claim.approve",
    )
