"""Database backup — ``pg_dump -Fc`` as the owner role (Increment 2).

Runs INSIDE the app/worker container (which carries ``postgresql-client-16``).
The dump is taken as ``oc_dev`` (``MIGRATION_DATABASE_URL``) — the owner/
superuser — because ``oc_app`` is SELECT-only and cannot produce a faithful,
fully-restorable dump. ``-Fc`` (custom format) is compressed, selectively
restorable, and a single MVCC-consistent snapshot, so the hash-chained audit
log is captured intact.

Files land in ``settings.backups_dir`` (bind-mounted to the host ``./backups``)
as ``office_connect_<UTC>.dump``. Writes go to a ``.partial`` name and are
atomically renamed on success, so a truncated dump never counts.
"""

from pathlib import Path

from office_connect.core.config import Settings, get_settings
from office_connect.core.time import utc_now
from office_connect.ops import dsn
from office_connect.ops.proc import run

_DUMP_GLOB = "office_connect_*.dump"


def _dump_name(now=None) -> str:
    stamp = (now or utc_now()).strftime("%Y%m%dT%H%M%SZ")
    return f"office_connect_{stamp}.dump"


def create_backup(settings: Settings | None = None) -> Path:
    """Take a ``pg_dump -Fc`` of the office_connect DB. Return the dump path."""
    settings = settings or get_settings()
    backups_dir = Path(settings.backups_dir)
    backups_dir.mkdir(parents=True, exist_ok=True)

    db = dsn.database_name(settings.migration_database_url)
    target = backups_dir / _dump_name()
    partial = target.with_suffix(target.suffix + ".partial")

    env = dsn.libpq_env(settings.migration_database_url, database=db)
    run(
        [
            "pg_dump",
            "--format=custom",
            "--no-password",
            f"--dbname={db}",
            f"--file={partial}",
        ],
        env=env,
        what="pg_dump",
    )
    partial.replace(target)  # atomic on the same filesystem
    return target


def list_backups(settings: Settings | None = None) -> list[Path]:
    """Newest first (filenames are UTC-stamped, so name sort == time sort)."""
    settings = settings or get_settings()
    return sorted(
        Path(settings.backups_dir).glob(_DUMP_GLOB),
        key=lambda p: p.name,
        reverse=True,
    )


def latest_backup(settings: Settings | None = None) -> Path | None:
    backups = list_backups(settings)
    return backups[0] if backups else None


def prune_old_backups(keep: int, settings: Settings | None = None) -> list[Path]:
    """Keep the newest ``keep`` dumps; unlink the rest. Return what was removed.

    Only ever called after a SUCCESSFUL backup+drill, never on a failing run.
    """
    settings = settings or get_settings()
    removed: list[Path] = []
    for old in list_backups(settings)[max(keep, 0) :]:
        old.unlink(missing_ok=True)
        removed.append(old)
    return removed
