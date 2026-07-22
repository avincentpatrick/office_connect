"""GET /api/v1/config — tenant identity + branding + feature flags (Day-1 #9).

Fail-safe OFF is the contract: any unreadable flag reports ``false``, a
missing/unreadable tenant row degrades to neutral defaults, and a whole-DB
failure returns all flags OFF — always HTTP 200, never a 500. Redis-cached
with a short TTL so flag flips propagate within seconds.
"""

import json

from fastapi import APIRouter, Request
from sqlalchemy import select

from office_connect import APP_VERSION
from office_connect.core.db import SessionLocal
from office_connect.core.models import FeatureFlag, TenantConfig

router = APIRouter()

CACHE_KEY = "oc:config:v1"
CACHE_TTL_SECONDS = 30

_NEUTRAL_TENANT = {
    "name": "Office-Connect",
    "short_name": "OC",
    "timezone": "Asia/Manila",
}


@router.get("/config")
async def get_config(request: Request) -> dict:
    redis = getattr(request.app.state, "redis", None)

    if redis is not None:
        try:
            cached = await redis.get(CACHE_KEY)
            if cached:
                return json.loads(cached)
        except Exception:  # noqa: BLE001 — cache failure must not break config
            pass

    tenant = dict(_NEUTRAL_TENANT)
    branding: dict = {}
    features: dict[str, bool] = {}
    try:
        async with SessionLocal() as session:
            row = (
                await session.execute(
                    select(TenantConfig).order_by(TenantConfig.id).limit(1)
                )
            ).scalar_one_or_none()  # soft-deleted rows filtered globally
            if row is not None:
                tenant = {
                    "name": row.name,
                    "short_name": row.short_name,
                    "timezone": row.timezone,
                }
                branding = row.branding or {}
            for flag in (await session.execute(select(FeatureFlag))).scalars():
                try:
                    features[flag.key] = bool(flag.enabled and flag.is_active)
                except Exception:  # noqa: BLE001 — per-flag fail-safe OFF
                    features[flag.key] = False
    except Exception:  # noqa: BLE001 — whole-DB fail-safe: all OFF, still 200
        tenant, branding, features = dict(_NEUTRAL_TENANT), {}, {}

    payload = {
        "tenant": tenant,
        "branding": branding,
        "features": features,
        "version": APP_VERSION,
    }

    if redis is not None:
        try:
            await redis.set(CACHE_KEY, json.dumps(payload), ex=CACHE_TTL_SECONDS)
        except Exception:  # noqa: BLE001
            pass
    return payload
