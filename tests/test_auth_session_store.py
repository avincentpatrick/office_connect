"""B2: Redis session store — round-trip, index, timeouts, cap, revoke, rotate."""

from datetime import timedelta


async def _new(store, user_id, roles=("staff",)):
    return await store.create_session(
        user_id=user_id, email="u@x", permissions_version=0, roles=roles,
        ip=None, user_agent=None,
    )


async def test_create_get_roundtrip(session_store):
    sid, _rec = await _new(session_store, 1, roles=("system_admin",))
    got = await session_store.get_session_record(sid)
    assert got is not None
    assert got.user_id == 1 and got.roles == ("system_admin",) and got.is_privileged


async def test_user_index_membership(session_store):
    sid, _ = await _new(session_store, 2)
    assert [r.sid for r in await session_store.list_for_user(2)] == [sid]


async def test_touch_slides_last_seen(session_store):
    sid, rec = await _new(session_store, 3)
    later = rec.created_at + timedelta(seconds=5)
    touched = await session_store.touch(sid, now=later)
    assert touched.last_seen_at == later


async def test_idle_timeout_auto_revokes(session_store):
    sid, rec = await _new(session_store, 4)  # staff idle = 60 min
    future = rec.created_at + timedelta(hours=2)
    assert await session_store.get_session_record(sid, now=future) is None


async def test_absolute_timeout_auto_revokes(session_store):
    sid, rec = await _new(session_store, 5)
    future = rec.created_at + timedelta(hours=13)  # > 12h absolute
    assert await session_store.get_session_record(sid, now=future) is None


async def test_destroy_all_except_current(session_store):
    a, _ = await _new(session_store, 6)
    b, _ = await _new(session_store, 6)
    revoked = await session_store.destroy_all_for_user(6, except_sid=a)
    assert revoked == 1
    assert await session_store.get_session_record(a) is not None
    assert await session_store.get_session_record(b) is None


async def test_cap_evicts_oldest(session_store):
    sids = [(await _new(session_store, 7))[0] for _ in range(5)]
    live = await session_store.list_for_user(7)
    assert len(live) == 3  # session_max_concurrent
    assert await session_store.get_session_record(sids[0]) is None  # oldest gone


async def test_regenerate_rotates_id(session_store):
    sid, _ = await _new(session_store, 8)
    new_sid, rec = await session_store.regenerate_id(sid, mfa_authenticated=True)
    assert new_sid != sid
    assert await session_store.get_session_record(sid) is None
    assert rec.user_id == 8


async def test_resolve_handle_is_user_scoped(session_store):
    sid, rec = await _new(session_store, 9)
    assert await session_store.resolve_handle(9, rec.session_id_hash) == sid
    # a different user cannot resolve another user's handle
    assert await session_store.resolve_handle(999, rec.session_id_hash) is None
