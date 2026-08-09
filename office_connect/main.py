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
from office_connect.core.api.query_log_middleware import QueryLogMiddleware
from office_connect.core.api.router import api_router
from office_connect.core.auth.middleware import AuthPrincipalMiddleware, CSRFMiddleware
from office_connect.core.auth.permission_cache import PermissionCache
from office_connect.core.auth.session_store import SessionStore
from office_connect.core.config import get_settings
from office_connect.core.db import engine
from office_connect.core.logging import configure_logging, request_id_ctx
from office_connect.core.observability import init_error_tracking

# Module routers mount HERE, the composition root — core/api/router.py may not
# include them (import-linter: core never imports modules; app → modules is
# legal, same reasoning as the ops import in lifespan). api-standards §9.
from office_connect.core.calendar import register_source
from office_connect.modules.reimbursement.api import router as reimbursement_router
from office_connect.modules.reimbursement.api.actions import (
    router as reimbursement_actions_router,
)
from office_connect.modules.reimbursement.calendar import (
    LIQUIDATION_SOURCE,
    TRAVEL_SOURCE,
)

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
    # RBAC (Increment 3): the effective-permission cache shares the db-4 auth
    # keyspace, invalidated by core_users.permissions_version.
    app.state.permission_cache = PermissionCache(app.state.session_redis, settings)
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
app.include_router(reimbursement_router)
# The approver's decision endpoints mount SEPARATELY and un-gated on purpose:
# a router's dependencies apply to everything included beneath it, and the
# feature flag must never strand in-flight approvals (workflow-standards §9).
app.include_router(reimbursement_actions_router)

# Calendar sources register HERE for the same reason the routers mount here:
# core/calendar owns the protocol and the merge, each module owns its own scope
# rule, and core may not import modules (import-linter). Same shape as the ops
# enqueuer injection in lifespan above. api-standards §9k.
register_source(TRAVEL_SOURCE)
register_source(LIQUIDATION_SOURCE)

# Structured error envelope for every raised HTTPException/APIError/validation
# error (api-standards §3) — the first exception handlers in the app.
register_error_handlers(app)

# Middleware. Starlette runs middleware in REVERSE registration order, so the
# FIRST add_middleware becomes the INNERMOST wrapper. Effective nesting:
# request_id (outermost) → CSRF → auth-principal → query-log → route. The query
# log is innermost so it sees the resolved route params + final status; gated by a
# config flag so it adds zero overhead when off.
if settings.query_log_enabled:
    app.add_middleware(QueryLogMiddleware)
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
