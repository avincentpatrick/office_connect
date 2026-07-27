"""Query-log middleware — append-only access log (Stage B / Increment 4).

Writes one ``core_query_logs`` row per ``/api/v1`` request (reads AND writes,
authenticated AND anonymous) — the COA read-access posture (Res. 2020-034). It
records WHO touched WHAT: ``module``/``resource``/``action`` + ids + param NAMES +
status + duration. It NEVER reads the request/response body, headers, cookies, or
query-parameter VALUES, so **no SPI/PII enters the log** (``?q=<a name>`` records
only that a ``q`` param was present).

Placed innermost (just outside the route) so it sees the resolved path params and
the final status. A logging failure is swallowed — an access log must never break
a request. ``core_query_logs`` is in the audit ``_UNAUDITED`` set, so a plain
pooled ``SessionLocal`` INSERT is exactly right (no audit-chain overhead). Pure
core — imports no ops/worker.
"""

from __future__ import annotations

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from office_connect.core.db import SessionLocal
from office_connect.core.models import QueryLog

logger = logging.getLogger(__name__)

_API_PREFIX = "/api/v1/"
_EXCLUDED_PATHS = frozenset({"/api/v1/config"})  # high-frequency, public, no PII
_ACTION_BY_METHOD = {
    "GET": "read",
    "HEAD": "read",
    "OPTIONS": "read",
    "POST": "create",
    "PUT": "update",
    "PATCH": "update",
    "DELETE": "delete",
}


def _derive(path: str, path_params: dict) -> tuple[str, str]:
    """(module, resource) from the URL, stripping id/param segments."""
    tail = path[len(_API_PREFIX) :] if path.startswith(_API_PREFIX) else path.lstrip("/")
    segs = [s for s in tail.split("/") if s]
    if not segs:
        return ("root", "root")
    module = segs[0]
    param_vals = {str(v) for v in path_params.values()}
    resource_segs = [s for s in segs[1:] if s not in param_vals]
    return module, ("/".join(resource_segs) or module)


class QueryLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            await self._safe_log(request, 500, start)  # record then re-raise
            raise
        await self._safe_log(request, response.status_code, start)
        return response

    async def _safe_log(
        self, request: Request, status_code: int, start: float
    ) -> None:
        try:
            path = request.url.path
            if (
                not path.startswith(_API_PREFIX)
                or path in _EXCLUDED_PATHS
                or request.method == "OPTIONS"
            ):
                return
            path_params = dict(request.path_params or {})
            module, resource = _derive(path, path_params)
            user = getattr(request.state, "user", None)
            detail = {
                "method": request.method,
                "path": path,  # concrete path incl. ids ("ids/params only")
                "path_params": {k: str(v) for k, v in path_params.items()},
                "query_keys": sorted(set(request.query_params.keys())),  # NAMES only
                "status_code": status_code,
                "duration_ms": int((time.perf_counter() - start) * 1000),
            }
            async with SessionLocal() as session:
                session.add(
                    QueryLog(
                        created_by=(user.user_id if user is not None else None),
                        module=module,
                        resource=resource,
                        action=_ACTION_BY_METHOD.get(request.method, "read"),
                        detail=detail,
                        request_id=getattr(request.state, "request_id", None),
                    )
                )
                await session.commit()
        except Exception:  # an access-log failure must never break the request
            logger.warning("query-log write failed", exc_info=True)
