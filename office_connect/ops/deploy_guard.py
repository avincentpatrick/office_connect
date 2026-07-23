"""Deploy guard — refuses to deploy when unsafe (Increment 2).

Run in-container so dev (Windows) and prod (Ubuntu VM) share identical logic:

    docker compose run --rm -v "<repo>:/repo:ro" app \
        python -m office_connect.ops.deploy_guard --repo /repo --mode dev|release

Modes:
- ``dev``     : Guard A only (the everyday backup -> migrate -> up sequence).
- ``release`` : Guard A + B + C (cutting a phase-gate release).

Guard A — live-DB / migrate safety (both modes):
  A1  refuse boot-migration in production (APP_ENV=production + OC_MIGRATE_ON_BOOT).
  A2  single Alembic head (``upgrade head`` is ambiguous with divergent history).
  A3  backup-before-migrate: if the schema is already deployed (alembic_version
      exists), require a fresh dump (< window) — never re-migrate a live DB
      without a current backup. A brand-new DB is treated as empty, so the first
      deploy is not blocked.

Guard B — version bump (release only): APP_VERSION must not carry ``.devN``.
Guard C — changelog (release only): ``[Unreleased]`` must have >=1 real entry.

The git-tag-existence check for a release lives in the host wrapper (``.git``
and ``git`` are not in the container).
"""

import argparse
import asyncio
import re
import sys
import time
from pathlib import Path

from office_connect import APP_VERSION
from office_connect.core.config import Settings, get_settings
from office_connect.ops import dsn

_BACKUP_FRESH_SECONDS = 3600  # a dump is "fresh" if modified within the last hour


def _fail(msg: str) -> None:
    print(f"  ✗ {msg}", file=sys.stderr)


def _ok(msg: str) -> None:
    print(f"  ✓ {msg}")


# --- Guard A -------------------------------------------------------------


def _a1_prod_boot_migration(env: dict) -> str | None:
    app_env = env.get("APP_ENV", "local")
    migrate_on_boot = env.get("OC_MIGRATE_ON_BOOT", "false").lower() in {
        "1", "true", "yes", "on",
    }
    if app_env == "production" and migrate_on_boot:
        return ("production must use the explicit migrate step — unset "
                "OC_MIGRATE_ON_BOOT (it is a dev-only convenience)")
    return None


def _a2_single_head(alembic_dir: str) -> str | None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config()
    cfg.set_main_option("script_location", alembic_dir)
    heads = ScriptDirectory.from_config(cfg).get_heads()
    if len(heads) != 1:
        return f"Alembic has {len(heads)} heads {heads} — expected exactly 1"
    return None


async def _schema_deployed(settings: Settings) -> bool:
    import asyncpg
    from sqlalchemy.engine import make_url

    url = make_url(settings.migration_database_url)
    conn = await asyncpg.connect(
        host=url.host, port=url.port or 5432, user=url.username,
        password=url.password, database=url.database,
    )
    try:
        return bool(await conn.fetchval("SELECT to_regclass('public.alembic_version')"))
    finally:
        await conn.close()


def _a3_backup_before_migrate(settings: Settings) -> str | None:
    deployed = asyncio.run(_schema_deployed(settings))
    if not deployed:
        return None  # fresh DB — nothing to protect yet
    backups = Path(settings.backups_dir)
    now = time.time()
    fresh = [
        p for p in backups.glob("office_connect_*.dump")
        if now - p.stat().st_mtime < _BACKUP_FRESH_SECONDS
    ]
    if not fresh:
        return ("schema is already deployed but no fresh backup exists — take a "
                "backup (python -m office_connect.ops backup) before migrating")
    return None


# --- Guard B / C ---------------------------------------------------------


def _b_version_bump() -> str | None:
    if not re.fullmatch(r"\d+\.\d+\.\d+", APP_VERSION):
        return (f"APP_VERSION is {APP_VERSION!r} — a release must drop the .devN "
                "suffix (development-workflow.md §6)")
    return None


def _c_changelog(repo: Path) -> str | None:
    changelog = repo / "CHANGELOG.md"
    if not changelog.is_file():
        return f"CHANGELOG.md not found at {changelog}"
    in_unreleased = False
    for line in changelog.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            if in_unreleased:
                break
            in_unreleased = "[Unreleased]" in line
            continue
        if in_unreleased and re.match(r"^\s*-\s+\S", line):
            return None
    return "CHANGELOG [Unreleased] has no entries — nothing user-visible to ship"


# --- driver --------------------------------------------------------------


def run_guards(mode: str, repo: Path, alembic_dir: str, env: dict,
               settings: Settings) -> int:
    failures = 0
    print(f"Deploy guard (mode={mode})")

    for name, problem in (
        ("A1 prod boot-migration", _a1_prod_boot_migration(env)),
        ("A2 single Alembic head", _a2_single_head(alembic_dir)),
        ("A3 backup-before-migrate", _a3_backup_before_migrate(settings)),
    ):
        if problem:
            _fail(f"{name}: {problem}")
            failures += 1
        else:
            _ok(name)

    if mode == "release":
        for name, problem in (
            ("B version bump", _b_version_bump()),
            ("C changelog [Unreleased]", _c_changelog(repo)),
        ):
            if problem:
                _fail(f"{name}: {problem}")
                failures += 1
            else:
                _ok(name)

    if failures:
        print(f"\nDEPLOY BLOCKED — {failures} guard(s) failed.", file=sys.stderr)
        return 1
    print("\nAll guards passed.")
    return 0


def main(argv: list[str] | None = None) -> int:
    import os

    parser = argparse.ArgumentParser(prog="office_connect.ops.deploy_guard")
    parser.add_argument("--mode", choices=["dev", "release"], default="dev")
    parser.add_argument("--repo", default="/repo",
                        help="repo root (read-only mount) for CHANGELOG.md")
    parser.add_argument("--alembic-dir", default="/app/alembic")
    args = parser.parse_args(argv)

    return run_guards(
        mode=args.mode,
        repo=Path(args.repo),
        alembic_dir=args.alembic_dir,
        env=dict(os.environ),
        settings=get_settings(),
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
