"""Celery tasks for the ops subsystem (Increment 2).

The nightly beat task takes a backup and prunes old dumps. It deliberately does
NOT run the restore drill (which manufactures synthetic data when the chain is
empty) — the drill is a one-time/quarterly proof run via the CLI, never a nightly
job against a live DB. The task is pure-subprocess, so no async event loop is
involved in the worker.
"""

from office_connect.core.config import get_settings
from office_connect.ops.backup import create_backup, prune_old_backups
from office_connect.worker import celery_app


@celery_app.task(
    name="ops.backup_database",
    bind=True,
    acks_late=True,
    soft_time_limit=3300,
    time_limit=3600,
    max_retries=2,
    default_retry_delay=300,
)
def backup_database(self) -> dict:
    settings = get_settings()
    dump = create_backup(settings)
    pruned = prune_old_backups(settings.backup_retention, settings)
    return {"dump": str(dump), "pruned": [str(p) for p in pruned]}


# Aggregate the other ops task modules here so the worker's autodiscover of
# ``office_connect.ops.tasks`` registers every task (Increment 4).
from office_connect.ops import attachments_tasks  # noqa: E402,F401
from office_connect.ops import document_tasks  # noqa: E402,F401
from office_connect.ops import notification_tasks  # noqa: E402,F401
from office_connect.ops import reimbursement_tasks  # noqa: E402,F401
from office_connect.ops import workflow_tasks  # noqa: E402,F401
