"""B3: Redis permission cache (version-keyed, boundary-TTL) + the loader."""

from datetime import timedelta

from sqlalchemy import select

from office_connect.core.auth.dependencies import load_permission_entry
from office_connect.core.auth.permission_cache import PermissionCache
from office_connect.core.config import get_settings
from office_connect.core.models import Role, UserRole
from office_connect.core.time import utc_now


async def test_hit_serves_from_redis_without_reloading(session_redis):
    cache = PermissionCache(session_redis, get_settings())
    calls = {"n": 0}

    async def loader():
        calls["n"] += 1
        return {"a.read", "b.write"}, None

    first = await cache.get_or_load(42, 0, loader)
    second = await cache.get_or_load(42, 0, loader)
    assert first == {"a.read", "b.write"} == second
    assert calls["n"] == 1  # the second call was a cache hit — no DB reload


async def test_version_bump_is_a_new_key(session_redis):
    cache = PermissionCache(session_redis, get_settings())

    async def v0():
        return {"old"}, None

    async def v1():
        return {"new"}, None

    assert await cache.get_or_load(7, 0, v0) == {"old"}
    # A bumped permissions_version => a different key => a fresh load; the old
    # entry is simply orphaned (TTL-collected), never served again.
    assert await cache.get_or_load(7, 1, v1) == {"new"}


async def test_ttl_capped_at_next_window_boundary(session_redis):
    cache = PermissionCache(session_redis, get_settings())
    boundary = utc_now() + timedelta(seconds=30)

    async def loader():
        return {"x"}, boundary

    await cache.get_or_load(9, 0, loader)
    ttl = await session_redis.ttl("authz:perm:9:v0")
    assert 0 < ttl <= 30  # capped by the delegation edge, not the 300s backstop


async def test_ttl_uses_backstop_without_boundary(session_redis):
    cache = PermissionCache(session_redis, get_settings())

    async def loader():
        return {"x"}, None

    await cache.get_or_load(10, 0, loader)
    ttl = await session_redis.ttl("authz:perm:10:v0")
    assert ttl > 30  # the backstop (300s default), nothing to cap it


async def test_loader_excludes_expired_delegation(app_session, seed_rbac, make_user):
    user, _ = await make_user()
    approver = (
        await app_session.execute(select(Role).where(Role.code == "approver"))
    ).scalar_one()
    app_session.add(
        UserRole(
            user_id=user.id,
            role_id=approver.id,
            valid_to=utc_now() - timedelta(hours=1),  # already expired
        )
    )
    await app_session.commit()
    codes, _boundary = await load_permission_entry(app_session, user.id)
    assert "reimb.claim.approve" not in codes


async def test_loader_active_grant_returns_future_boundary(
    app_session, seed_rbac, make_user
):
    user, _ = await make_user()
    approver = (
        await app_session.execute(select(Role).where(Role.code == "approver"))
    ).scalar_one()
    valid_to = utc_now() + timedelta(minutes=45)
    app_session.add(
        UserRole(user_id=user.id, role_id=approver.id, valid_to=valid_to)
    )
    await app_session.commit()
    codes, boundary = await load_permission_entry(app_session, user.id)
    assert "reimb.claim.approve" in codes
    assert boundary is not None
    assert abs((boundary - valid_to).total_seconds()) < 2
