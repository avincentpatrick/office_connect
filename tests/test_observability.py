"""Increment 4 Group H — structured JSON logs + request-id + fail-safe tracker."""

import json
import logging

from office_connect.core.config import Settings
from office_connect.core.logging import (
    JsonFormatter,
    configure_logging,
    request_id_ctx,
)
from office_connect.core.observability import init_error_tracking


def _record(msg="hello", **extra):
    return logging.LogRecord(
        name="office_connect.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=(),
        exc_info=None,
    )


def test_json_formatter_emits_structured_line():
    token = request_id_ctx.set("req-123")
    try:
        out = JsonFormatter().format(_record("something happened"))
    finally:
        request_id_ctx.reset(token)
    payload = json.loads(out)
    assert payload["message"] == "something happened"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "office_connect.test"
    assert payload["request_id"] == "req-123"
    assert "ts" in payload


def test_json_formatter_omits_request_id_when_unset():
    token = request_id_ctx.set(None)
    try:
        payload = json.loads(JsonFormatter().format(_record()))
    finally:
        request_id_ctx.reset(token)
    assert "request_id" not in payload


def test_configure_logging_is_idempotent():
    configure_logging(level="INFO", json_logs=True)
    configure_logging(level="INFO", json_logs=True)
    root = logging.getLogger()
    ours = [h for h in root.handlers if getattr(h, "_oc_handler", False)]
    assert len(ours) == 1  # re-config replaces, never duplicates


def test_error_tracking_no_op_without_dsn():
    assert init_error_tracking(Settings(sentry_dsn=None)) is False
