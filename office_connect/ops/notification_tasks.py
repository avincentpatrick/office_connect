"""Notification dispatch task (Increment 4).

Wraps the pure ``core.dispatch_outbox_row`` with Celery retry + exponential
back-off; on exhaustion it moves the row to the dead-letter state. ``core`` may
not import the worker (import-linter), so this ops module also **registers the
enqueuer into core** (ops → core injection) — the running app then enqueues a
dispatch after the outbox row commits.
"""

from __future__ import annotations

import asyncio
from typing import Any

from office_connect.core.config import get_settings
from office_connect.core.email import EmailError
from office_connect.core.notifications import (
    dispatch_outbox_row,
    mark_dead,
    register_enqueuer,
)
from office_connect.worker import celery_app

_MAX_ATTEMPTS = get_settings().notifications_max_attempts


@celery_app.task(
    name="ops.dispatch_notification",
    bind=True,
    acks_late=True,
    max_retries=_MAX_ATTEMPTS,
)
def dispatch_notification(self, notification_id: int) -> dict[str, Any]:
    settings = get_settings()
    try:
        result = asyncio.run(dispatch_outbox_row(notification_id, settings=settings))
        return {
            "notification_id": notification_id,
            "driver": result.driver,
            "sent": result.sent,
        }
    except EmailError as exc:
        base = settings.notifications_retry_base_seconds
        cap = settings.notifications_retry_max_seconds
        countdown = min(base * (2 ** self.request.retries), cap)
        try:
            raise self.retry(exc=exc, countdown=countdown)
        except self.MaxRetriesExceededError:
            asyncio.run(mark_dead(notification_id, str(exc), settings=settings))
            raise


# ops → core injection: the app enqueues dispatches through this after commit.
register_enqueuer(
    lambda notification_id: celery_app.send_task(
        "ops.dispatch_notification", args=[notification_id]
    )
)
