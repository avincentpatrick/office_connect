"""QA gate: /api/v1/config — shape, flag flips, and fail-safe OFF (Day-1 #9)."""

import pytest
import redis.asyncio as aioredis
from sqlalchemy import text

import office_connect.core.api.config as config_api
from office_connect import APP_VERSION
from office_connect.core.config import get_settings
from office_connect.core.ui.tokens import NEUTRAL_TOKENS

SEED_FLAG_KEYS = ("module.reimbursement", "module.css_is", "module.dmwis")


@pytest.fixture(autouse=True)
async def _reset_flags_and_cache(owner_session):
    """Isolate each test from the 30s cache AND from leftover flag state —
    a hard-killed prior run can leave a flipped flag committed (the finally
    blocks below never ran)."""
    await owner_session.execute(
        text(
            "UPDATE core_feature_flags SET enabled = false, is_active = true, "
            "deleted_at = NULL, deleted_by = NULL WHERE key = ANY(:keys)"
        ),
        {"keys": list(SEED_FLAG_KEYS)},
    )
    await owner_session.commit()
    r = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    await r.delete(config_api.CACHE_KEY)
    yield
    await r.delete(config_api.CACHE_KEY)
    await r.aclose()


async def _set_flag(owner_session, key: str, *, enabled: bool, is_active: bool = True):
    await owner_session.execute(
        text(
            "UPDATE core_feature_flags SET enabled = :enabled, is_active = :active "
            "WHERE key = :key"
        ),
        {"enabled": enabled, "active": is_active, "key": key},
    )
    await owner_session.commit()


async def test_shape_and_defaults(client):
    body = (await client.get("/api/v1/config")).json()
    assert body["tenant"]["name"] == "Office-Connect"
    assert body["tenant"]["timezone"] == "Asia/Manila"
    assert body["version"] == APP_VERSION
    assert set(body["features"]) == {
        "module.reimbursement",
        "module.css_is",
        "module.dmwis",
    }
    assert all(v is False for v in body["features"].values())  # seeded OFF


async def test_flag_flip_reflected(client, owner_session):
    try:
        await _set_flag(owner_session, "module.reimbursement", enabled=True)
        body = (await client.get("/api/v1/config")).json()
        assert body["features"]["module.reimbursement"] is True
    finally:
        await _set_flag(owner_session, "module.reimbursement", enabled=False)


async def test_retired_flag_reports_off(client, owner_session):
    """enabled=true but is_active=false → OFF (both must hold)."""
    try:
        await _set_flag(owner_session, "module.dmwis", enabled=True, is_active=False)
        body = (await client.get("/api/v1/config")).json()
        assert body["features"]["module.dmwis"] is False
    finally:
        await _set_flag(owner_session, "module.dmwis", enabled=False, is_active=True)


async def test_soft_deleted_flag_disappears(client, owner_session):
    """Soft-deleted rows are invisible to the endpoint (global filter)."""
    try:
        await owner_session.execute(
            text(
                "UPDATE core_feature_flags SET deleted_at = now() "
                "WHERE key = 'module.css_is'"
            )
        )
        await owner_session.commit()
        body = (await client.get("/api/v1/config")).json()
        # Other flags present proves the DB path ran (not the fail-safe branch,
        # which would also make the assertion below pass vacuously).
        assert "module.reimbursement" in body["features"]
        assert "module.css_is" not in body["features"]
    finally:
        await owner_session.execute(
            text(
                "UPDATE core_feature_flags SET deleted_at = NULL "
                "WHERE key = 'module.css_is'"
            )
        )
        await owner_session.commit()


async def test_db_failure_fail_safe_off(client, monkeypatch):
    """Whole-DB failure → all flags OFF, neutral tenant, HTTP 200 — never 500."""

    def _boom():
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(config_api, "SessionLocal", _boom)
    response = await client.get("/api/v1/config")
    assert response.status_code == 200
    body = response.json()
    assert body["features"] == {}
    assert body["tenant"] == config_api._NEUTRAL_TENANT


async def test_tokens_served_with_defaults(client):
    """The design-token contract (ui-standards §2) rides on /api/v1/config."""
    body = (await client.get("/api/v1/config")).json()
    tokens = body["tokens"]
    assert tokens["color"]["brand"] == NEUTRAL_TOKENS["color"]["brand"]
    assert set(tokens["status"]) == {"done", "warn", "blocked", "waiting"}
    assert tokens["space"]["1"] == "4px"


async def test_tokens_present_even_on_db_failure(client, monkeypatch):
    """A degraded config still serves usable neutral tokens (never token-less)."""

    def _boom():
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(config_api, "SessionLocal", _boom)
    body = (await client.get("/api/v1/config")).json()
    assert body["tokens"]["color"]["brand"] == NEUTRAL_TOKENS["color"]["brand"]
    assert "waiting" in body["tokens"]["status"]


async def test_branding_overrides_tokens(client, owner_session):
    """Tenant branding.tokens overrides the neutral brand token."""
    try:
        await owner_session.execute(
            text(
                "UPDATE core_tenant_configs "
                "SET branding = '{\"tokens\": {\"color\": {\"brand\": \"#abcdef\"}}}'::jsonb "
                "WHERE id = (SELECT id FROM core_tenant_configs ORDER BY id LIMIT 1)"
            )
        )
        await owner_session.commit()
        r = aioredis.from_url(get_settings().redis_url, decode_responses=True)
        await r.delete(config_api.CACHE_KEY)
        await r.aclose()

        body = (await client.get("/api/v1/config")).json()
        assert body["tokens"]["color"]["brand"] == "#abcdef"
        # Untouched tokens still fall back to neutral defaults.
        assert body["tokens"]["color"]["bg"] == NEUTRAL_TOKENS["color"]["bg"]
    finally:
        await owner_session.execute(
            text(
                "UPDATE core_tenant_configs SET branding = '{}'::jsonb "
                "WHERE id = (SELECT id FROM core_tenant_configs ORDER BY id LIMIT 1)"
            )
        )
        await owner_session.commit()
