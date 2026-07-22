"""Office-Connect API entrypoint.

Phase-0 skeleton: proves the FastAPI + PostgreSQL + Redis stack boots and is
wired correctly. Real modules (core auth/directory, CSS-IS, DMWIS, ...) are
built on top per the execution plan.
"""

from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import engine

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    yield
    await app.state.redis.aclose()
    await engine.dispose()


app = FastAPI(title=settings.app_name, lifespan=lifespan)


@app.get("/")
async def root():
    return {
        "service": settings.app_name,
        "env": settings.app_env,
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
async def health():
    """Liveness + dependency check. 200 when DB and Redis both answer, else 503."""
    checks: dict[str, str] = {}
    ok = True

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as exc:  # noqa: BLE001 - surface any connection failure
        ok = False
        checks["postgres"] = f"error: {type(exc).__name__}: {exc}"

    try:
        pong = await app.state.redis.ping()
        checks["redis"] = "ok" if pong else "error: no pong"
        ok = ok and bool(pong)
    except Exception as exc:  # noqa: BLE001
        ok = False
        checks["redis"] = f"error: {type(exc).__name__}: {exc}"

    return JSONResponse(
        status_code=200 if ok else 503,
        content={"status": "healthy" if ok else "degraded", "checks": checks},
    )
