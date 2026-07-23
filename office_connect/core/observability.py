"""Error tracking (Increment 4) — fail-safe optional, self-hosted.

``init_error_tracking`` initializes the Sentry SDK (GlitchTip is Sentry-SDK
compatible) only when ``SENTRY_DSN`` is set. No DSN → a no-op; a bad DSN or a
missing SDK → a warning, never a startup crash (feature flags fail-safe OFF).
"""

from __future__ import annotations

import logging

from office_connect.core.config import Settings, get_settings

log = logging.getLogger("office_connect.observability")


def init_error_tracking(settings: Settings | None = None) -> bool:
    """Initialize error tracking if configured. Returns True when active."""
    settings = settings or get_settings()
    if not settings.sentry_dsn:
        return False
    try:
        import sentry_sdk  # lazy — only needed when a DSN is configured

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.app_env,
            traces_sample_rate=0.0,  # errors only for now; tune at Stage C
        )
        return True
    except Exception as exc:  # never let observability init break the app
        log.warning("error tracker init skipped: %s", exc)
        return False
