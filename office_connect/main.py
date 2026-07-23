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
from office_connect.core.api.errors import register_error_handlers
from office_connect.core.api.router import api_router
from office_connect.core.auth.middleware import AuthPrincipalMiddleware, CSRFMiddleware
from office_connect.core.auth.session_store import SessionStore
from office_connect.core.config import get_settings
from office_connect.core.db import engine
from office_connect.core.logging import configure_logging, request_id_ctx
from office_connect.core.observability import init_error_tracking

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Observability (Increment 4): structured JSON logs + optional error tracker.
    configure_logging(level=settings.log_level, json_logs=settings.log_json)
    init_error_tracking(settings)
    app.state.redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    # Auth sessions (Increment 2): a SEPARATE Redis client on db 4 (not the db-0
    # config cache) + the server-side session store the auth middleware reads.
    app.state.session_redis = aioredis.from_url(
        settings.resolved_session_redis_url, decode_responses=True
    )
    app.state.session_store = SessionStore(app.state.session_redis, settings)
    # Register the notification enqueuer (ops → core injection) so celery-mode
    # dispatch works: send_notification enqueues to the worker after commit.
    # app → ops import is import-linter-legal (only `core` may not import ops).
    import office_connect.ops.tasks  # noqa: F401
    yield
    await app.state.session_redis.aclose()
    await app.state.redis.aclose()
    await engine.dispose()


app = FastAPI(title=settings.app_name, version=APP_VERSION, lifespan=lifespan)
app.include_router(api_router)

# Structured error envelope for every raised HTTPException/APIError/validation
# error (api-standards §3) — the first exception handlers in the app.
register_error_handlers(app)

# Auth + CSRF middleware. Starlette runs middleware in REVERSE registration order,
# so adding these two here (before request_id_middleware is defined below) yields
# the nesting: request_id (outermost) → CSRF → auth-principal → route.
app.add_middleware(AuthPrincipalMiddleware, cookie_name=settings.session_cookie_name)
app.add_middleware(CSRFMiddleware, header_name=settings.csrf_header_name)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Tag every request; audit rows carry it via get_session/set_audit_context
    (Phase 2 adds the actor once auth exists). An inbound X-Request-ID (e.g.
    from a reverse proxy) is honored; unhandled-500 responses lose the header —
    known BaseHTTPMiddleware limit, revisit with auth middleware in Phase 2."""
    request.state.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    request_id_ctx.set(request.state.request_id)  # so JSON logs carry it
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

    # Only the exception TYPE is exposed — this endpoint is unauthenticated,
    # and raw messages can leak DSNs/hosts. Details go to the server log.
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as exc:  # noqa: BLE001 - surface any connection failure
        ok = False
        checks["postgres"] = f"error: {type(exc).__name__}"

    try:
        pong = await app.state.redis.ping()
        checks["redis"] = "ok" if pong else "error: no pong"
        ok = ok and bool(pong)
    except Exception as exc:  # noqa: BLE001
        ok = False
        checks["redis"] = f"error: {type(exc).__name__}"

    return JSONResponse(
        status_code=200 if ok else 503,
        content={"status": "healthy" if ok else "degraded", "checks": checks},
    )
