"""Advisory-locked ``alembic upgrade head`` — the dev-only boot-migration path.

Production runs migrations as an EXPLICIT deploy step (``alembic upgrade head``
before app start); this module is the demoted dev convenience the container
entrypoint invokes when ``OC_MIGRATE_ON_BOOT=true`` so ``docker compose up`` from
a wiped volume yields a working read-write DB with no manual step.

Why this shape (foundation.md §3, master-plan §5):
- A **session-level ``pg_advisory_lock``** serializes concurrent boots (app +
  worker, or a future multi-worker app). The second waiter blocks, then finds
  the DB already at head and its own ``upgrade head`` is a no-op (idempotent).
  The lock is session-scoped, so a crash mid-migrate auto-releases it.
- Alembic runs in a **subprocess**: its ``env.py`` does its own ``asyncio.run``,
  which cannot be nested inside a running loop. We hold the lock on a separate
  ``asyncpg`` connection while that subprocess runs.
"""

import asyncio
import subprocess

import asyncpg
from sqlalchemy.engine import make_url

from office_connect.core.config import get_settings

# Fixed bigint key — the advisory-lock namespace for schema migrations.
_MIGRATE_LOCK_KEY = 728_155_900


async def _locked_upgrade() -> None:
    url = make_url(get_settings().migration_database_url)
    conn = await asyncpg.connect(
        host=url.host,
        port=url.port or 5432,
        user=url.username,
        password=url.password,
        database=url.database,
    )
    try:
        await conn.execute("SELECT pg_advisory_lock($1)", _MIGRATE_LOCK_KEY)
        proc = subprocess.run(["alembic", "upgrade", "head"], cwd="/app")
        if proc.returncode != 0:
            raise SystemExit(f"alembic upgrade head failed (exit {proc.returncode})")
    finally:
        await conn.execute("SELECT pg_advisory_unlock($1)", _MIGRATE_LOCK_KEY)
        await conn.close()


def main() -> None:
    asyncio.run(_locked_upgrade())


if __name__ == "__main__":
    main()
