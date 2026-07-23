"""Proven-restore drill (Increment 2 QA gate).

Backs up the DB, restores the dump into a throwaway **scratch** database, and
re-runs ``verify_chain()`` over the restored ``core_audit_logs`` — a free
end-to-end integrity check that the dump/restore round-trip is faithful.

Two correctness guarantees make the "green" meaningful:

1. **Non-empty chain.** On a freshly-migrated DB the audit log is empty (0001
   seeds run as the owner, outside the chain), so ``verify_chain([])`` would be
   *vacuously* green and prove nothing. Before dumping we therefore generate a
   real >=3-link chain through ``OCSession`` (insert + update + soft_delete,
   touching JSONB / a Decimal-shaped string / unicode / a timestamp) — but only
   when the chain is empty and the environment is not production (never seed real
   or production data).
2. **Faithful round-trip.** ``verify_chain`` re-canonicalizes the *logical*
   column values in Python (floats/Decimals already stringified in
   ``serialize_value``), so JSONB storage form / key order / whitespace are
   irrelevant and ``timestamptz`` preserves the instant — the chain holds across
   ``pg_dump -Fc`` -> ``pg_restore``.

The scratch DB is created/restored/dropped as the owner (``oc_dev`` — the only
role that can CREATE/DROP DATABASE); a hard name guard makes it impossible to
point the drop at the real database. Any failure raises loudly.
"""

import asyncio
from datetime import date
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

# Importing these registers the OCSession audit + soft-delete listeners.
from office_connect.core.audit import verify_chain
from office_connect.core.config import Settings, get_settings
from office_connect.core.models import Activity, AuditLog
from office_connect.core.session import OCSession, set_audit_context
from office_connect.core.soft_delete import soft_delete
from office_connect.core.time import utc_now
from office_connect.ops import dsn
from office_connect.ops.backup import create_backup, prune_old_backups
from office_connect.ops.proc import run


async def _seed_synthetic_chain(settings: Settings) -> int:
    """Ensure a non-trivial audited chain exists; return its row count.

    No-ops (returns the existing count) if the chain is already non-empty or the
    environment is production — this drill only manufactures data when there is
    none and we are in dev/test.
    """
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        sync_session_class=OCSession,
        expire_on_commit=False,
    )
    try:
        async with factory() as session:
            set_audit_context(session, request_id="restore-drill-seed")
            existing = (
                await session.execute(select(func.count()).select_from(AuditLog))
            ).scalar_one()
            if existing > 0 or settings.app_env == "production":
                return existing

            activity = Activity(
                title="Restore-drill ✓ actividé",
                date_start=date(2026, 1, 1),
                custom={"amount": "1234.56", "tags": ["dr_ill"], "n": 42},
            )
            session.add(activity)
            await session.flush()  # -> audit insert
            activity.venue = "Updated venue ✎"
            activity.custom = {"amount": "1234.56", "tags": ["dr_ill", "更新"], "n": 43}
            await session.flush()  # -> audit update
            soft_delete(activity)
            await session.flush()  # -> audit soft_delete
            await session.commit()

            return (
                await session.execute(select(func.count()).select_from(AuditLog))
            ).scalar_one()
    finally:
        await engine.dispose()


async def _verify_scratch(scratch_url: str) -> tuple[int, int | None]:
    """Load every audit row from the scratch DB (ordered) and verify the chain."""
    engine = create_async_engine(scratch_url, poolclass=NullPool)
    try:
        async with AsyncSession(engine) as session:  # plain: no listeners/filter
            rows = (
                await session.execute(select(AuditLog).order_by(AuditLog.id))
            ).scalars().all()
        return len(rows), verify_chain(list(rows))
    finally:
        await engine.dispose()


def run_restore_drill(dump_path: Path, settings: Settings | None = None) -> dict:
    """Restore ``dump_path`` into a fresh scratch DB and verify the audit chain."""
    settings = settings or get_settings()
    main_db = dsn.database_name(settings.migration_database_url)
    scratch = f"{settings.scratch_db_prefix}_{utc_now().strftime('%Y%m%d%H%M%S')}"

    # Hard guard: the drop must never be able to hit the real database.
    if scratch == main_db or not scratch.startswith(settings.scratch_db_prefix):
        raise RuntimeError(f"refusing unsafe scratch DB name {scratch!r}")

    maint_env = dsn.libpq_env(settings.migration_database_url, database="postgres")
    scratch_env = dsn.libpq_env(settings.migration_database_url, database=scratch)
    owner = maint_env.get("PGUSER", "oc_dev")
    scratch_url = dsn.swap_database(settings.migration_database_url, scratch)

    # Clean any residue from a prior crash, then create fresh.
    run(["dropdb", "--force", "--if-exists", "--no-password", scratch],
        env=maint_env, what="dropdb(pre)")
    run(["createdb", "--no-password", f"--owner={owner}", scratch],
        env=maint_env, what="createdb")
    try:
        run(
            [
                "pg_restore",
                "--no-password",
                f"--dbname={scratch}",
                "--single-transaction",
                "--exit-on-error",
                str(dump_path),
            ],
            env=scratch_env,
            what="pg_restore",
        )
        rows, broken = asyncio.run(_verify_scratch(scratch_url))
        if rows == 0:
            raise RuntimeError(
                "restore drill proved nothing: restored audit chain is EMPTY"
            )
        if broken is not None:
            raise RuntimeError(
                f"restore drill FAILED: audit chain broken at restored row id {broken}"
            )
        return {
            "dump": str(dump_path),
            "scratch_db": scratch,
            "audit_rows": rows,
            "verify": "ok",
        }
    finally:
        run(["dropdb", "--force", "--if-exists", "--no-password", scratch],
            env=maint_env, what="dropdb(cleanup)")


def run_backup_and_drill(settings: Settings | None = None) -> dict:
    """Seed (if needed) -> backup -> restore drill -> prune. The proof entrypoint."""
    settings = settings or get_settings()
    seeded = asyncio.run(_seed_synthetic_chain(settings))
    dump = create_backup(settings)
    result = run_restore_drill(dump, settings)
    pruned = prune_old_backups(settings.backup_retention, settings)
    return {"seeded_chain_rows": seeded, "pruned": [str(p) for p in pruned], **result}
