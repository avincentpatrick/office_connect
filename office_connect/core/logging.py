"""Structured JSON logging with request IDs (Increment 4 observability standard).

Every log line is one JSON object carrying a timestamp (UTC), level, logger,
message, and — when set — the ``request_id`` of the request in flight. The id is
carried in a ContextVar the request-id middleware sets, so it flows through
``await`` without threading it into every call. Stdlib-only (no dependency).
"""

from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from datetime import datetime, timezone

# Set by the request-id middleware (main.py); read by the formatter.
request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)

_RESERVED = frozenset(vars(logging.makeLogRecord({})).keys()) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = request_id_ctx.get()
        if request_id:
            payload["request_id"] = request_id
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # Any structured extras passed via logger.info(..., extra={...}).
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(*, level: str = "INFO", json_logs: bool = True) -> None:
    """Install the JSON (or plain) handler on the root logger. Idempotent —
    replaces only our own handler, leaving foreign handlers (e.g. pytest's
    caplog) intact. Also routes uvicorn's own loggers through the root handler so
    access/error lines are JSON too."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, "_oc_handler", False):
            root.removeHandler(handler)
    handler = logging.StreamHandler()
    handler._oc_handler = True  # type: ignore[attr-defined]
    handler.setFormatter(
        JsonFormatter()
        if json_logs
        else logging.Formatter("%(levelname)s %(name)s %(message)s")
    )
    root.addHandler(handler)
    root.setLevel(level.upper())

    # Uvicorn/gunicorn install their own handlers — drop them and let their
    # records bubble to the root handler so every line uses one format.
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error", "gunicorn.error"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
