"""Celery application + beat schedule (Increment 2).

Started via ``celery -A office_connect.worker.celery_app`` in the ``worker`` and
``beat`` compose services. The broker/results live on **separate** Redis logical
DBs (1 / 2) from the app config cache (db 0) so keyspaces never collide.

The first scheduled task is the nightly DB backup (``ops.backup_database``); it
is pure-subprocess (``pg_dump``), so it avoids the Celery-prefork + asyncio
event-loop-binding trap entirely. Tasks that need async SQLAlchemy must build a
fresh ``NullPool`` engine inside ``asyncio.run`` (see ``ops.restore_drill``) —
never reuse the app's pooled engine from a worker.
"""

from celery import Celery
from celery.schedules import crontab

from office_connect.core.config import get_settings
from office_connect.ops.dsn import redis_url_with_db

settings = get_settings()

_broker = settings.celery_broker_url or redis_url_with_db(settings.redis_url, 1)
_backend = settings.celery_result_backend or redis_url_with_db(settings.redis_url, 2)

celery_app = Celery("office_connect", broker=_broker, backend=_backend)
celery_app.conf.update(
    broker_connection_retry_on_startup=True,  # retry while Redis warms (Celery 5.4)
    timezone="Asia/Manila",  # PH has no DST; schedules read local, filenames stay UTC
    enable_utc=True,
    result_expires=3600,
    task_acks_late=True,  # a killed worker re-queues the long backup task
    worker_prefetch_multiplier=1,
    task_track_started=True,
    beat_schedule={
        "nightly-db-backup": {
            "task": "ops.backup_database",
            "schedule": crontab(minute=0, hour=2),  # 02:00 Asia/Manila
            "options": {"expires": 3600},  # a missed slot does not pile up
        },
        # Drain any attachments still 'pending'/'error' (until the Stage-B upload
        # router enqueues per-upload). Cheap no-op when there are none.
        "scan-pending-attachments": {
            "task": "ops.scan_pending_attachments",
            "schedule": crontab(minute="*/5"),
            "options": {"expires": 240},
        },
    },
)

# Discovers office_connect.ops.tasks (the "tasks" module of the ops package).
celery_app.autodiscover_tasks(["office_connect.ops"])
