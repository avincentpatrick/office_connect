"""Auth-principal + CSRF middleware (Starlette ``BaseHTTPMiddleware``).

Registered in ``main.py`` so the effective nesting is
**request_id (outermost) → CSRF → auth-principal → route**:

- ``request_id`` stays outermost so every response — including auth/CSRF
  rejections — carries ``X-Request-ID`` and the logging contextvar.
- ``CSRFMiddleware`` is a pure header check (no IO): a forged/headerless unsafe
  request is rejected before any Redis lookup. Login is NOT exempt (the SPA fetch
  wrapper sends the header on every call), which also blocks login-CSRF.
- ``AuthPrincipalMiddleware`` sets ``request.state.user = Principal | None`` for
  ALL routes and never raises for anonymous callers; a session-store blip fails
  **closed** (user=None → protected routes 401, never a 500). The 401/403 for
  protected routes is done by the dependencies, not here.
"""

from __future__ import annotations

import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from office_connect.core.api.errors import error_envelope
from office_connect.core.auth.principal import Principal

logger = logging.getLogger(__name__)

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


class CSRFMiddleware(BaseHTTPMiddleware):
    """Require a custom header on every non-safe method (SameSite=Lax floor + this)."""

    def __init__(self, app, *, header_name: str) -> None:
        super().__init__(app)
        self._header_name = header_name

    async def dispatch(self, request: Request, call_next):
        if request.method not in _SAFE_METHODS and not request.headers.get(
            self._header_name
        ):
            return error_envelope(
                status_code=403,
                code="csrf_failed",
                message="Missing required request header.",
                request_id=getattr(request.state, "request_id", None),
            )
        return await call_next(request)


class AuthPrincipalMiddleware(BaseHTTPMiddleware):
    """Resolve the session cookie → ``request.state.user`` (Principal or None)."""

    def __init__(self, app, *, cookie_name: str) -> None:
        super().__init__(app)
        self._cookie_name = cookie_name

    async def dispatch(self, request: Request, call_next):
        request.state.user = None
        sid = request.cookies.get(self._cookie_name)
        store = getattr(request.app.state, "session_store", None)
        if sid and store is not None:
            try:
                rec = await store.touch(sid)  # slides last_seen_at; None if expired
                if rec is not None:
                    request.state.user = Principal.from_record(rec)
            except Exception:  # fail closed — a store blip must not 500 the request
                logger.exception("session resolution failed")
        return await call_next(request)
