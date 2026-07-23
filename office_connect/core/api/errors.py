"""Structured error envelope + exception handlers (api-standards §3).

The first structured-error surface in the codebase (config/health never raise).
Every error response is ``{"error": {"code", "message", "details?"}, "request_id"}``
with the HTTP status carrying the class; ``error.code`` is a stable machine slug
clients branch on. Nothing here leaks DSNs, hostnames, stack traces, or SPI — the
422 handler drops the offending ``input`` so a bad login body never echoes the
attempted password, and the 500 handler returns fixed generic text.

``APIError`` is the app's canonical raise (CSRF middleware, auth dependencies, and
the auth endpoints all use it). ``register_error_handlers(app)`` installs the
handlers; it also sets ``X-Request-ID`` on the 500 response itself, closing the
BaseHTTPMiddleware gap where an unhandled 500 would otherwise lose the header.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

_STATUS_DEFAULT_CODE: dict[int, str] = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "validation_error",
    429: "rate_limited",
    500: "internal_error",
}

_STATUS_DEFAULT_MESSAGE: dict[int, str] = {
    400: "Bad request.",
    401: "Authentication required.",
    403: "Forbidden.",
    404: "Not found.",
    405: "Method not allowed.",
    409: "Conflict.",
    422: "Request validation failed.",
    429: "Too many requests.",
    500: "An internal error occurred.",
}


class APIError(Exception):
    """A structured HTTP error. ``code`` is the stable slug clients branch on."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        details: list[Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        self.headers = headers
        super().__init__(message)


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def error_envelope(
    *,
    status_code: int,
    code: str,
    message: str,
    request_id: str | None,
    details: list[Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    error: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return JSONResponse(
        status_code=status_code,
        content={"error": error, "request_id": request_id},
        headers=headers,
    )


async def _api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    return error_envelope(
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        request_id=_request_id(request),
        details=exc.details,
        headers=exc.headers,
    )


async def _http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    status = exc.status_code
    code = _STATUS_DEFAULT_CODE.get(status, "error")
    message = _STATUS_DEFAULT_MESSAGE.get(status, "Error.")
    details = None
    if isinstance(exc.detail, dict):
        code = exc.detail.get("code", code)
        message = exc.detail.get("message", message)
        details = exc.detail.get("details")
    elif isinstance(exc.detail, str) and exc.detail:
        message = exc.detail
    return error_envelope(
        status_code=status,
        code=code,
        message=message,
        request_id=_request_id(request),
        details=details,
        headers=getattr(exc, "headers", None),
    )


async def _validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    # Keep only loc/msg/type — NEVER echo `input`/`ctx` (could carry a password).
    details = [
        {"loc": list(err.get("loc", [])), "msg": err.get("msg"), "type": err.get("type")}
        for err in exc.errors()
    ]
    return error_envelope(
        status_code=422,
        code="validation_error",
        message="Request validation failed.",
        request_id=_request_id(request),
        details=details,
    )


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled exception")  # full detail server-side only
    response = error_envelope(
        status_code=500,
        code="internal_error",
        message="An internal error occurred.",
        request_id=_request_id(request),
    )
    rid = _request_id(request)
    if rid:
        response.headers["X-Request-ID"] = rid  # close the BaseHTTPMiddleware 500 gap
    return response


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(APIError, _api_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)
