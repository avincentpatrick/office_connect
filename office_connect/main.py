"""Office-Connect API entrypoint.

Phase-0: FastAPI + PostgreSQL + Redis wiring, health, and the /api/v1 spine
(config endpoint). Real modules (core auth/directory, CSS-IS, DMWIS, ...) are
built on top per the execution plan.
"""

import uuid
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from office_connect import APP_VERSION
from office_connect.core.api.router import api_router
from office_connect.core.config import get_settings
from office_connect.core.db import engine

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    yield
    await app.state.redis.aclose()
    await engine.dispose()


app = FastAPI(title=settings.app_name, version=APP_VERSION, lifespan=lifespan)
app.include_router(api_router)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Tag every request; audit rows carry it via set_audit_context (Phase 2
    adds the actor once auth exists)."""
    request.state.request_id = uuid.uuid4().hex
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


@app.get("/")
async def root():
    return {
        "service": settings.app_name,
        "version": APP_VERSION,
        "env": settings.app_env,
        "docs": "/docs",
        "health": "/health",
        "config": "/api/v1/config",
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
