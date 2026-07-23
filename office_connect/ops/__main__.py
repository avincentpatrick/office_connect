"""Manual ops CLI (Increment 2).

    docker compose exec worker python -m office_connect.ops backup
    docker compose exec worker python -m office_connect.ops restore-drill [--file latest|<path>]
    docker compose exec worker python -m office_connect.ops backup-and-drill

``backup-and-drill`` is the acceptance proof: produce a dump, restore it into a
scratch DB, and verify the audit chain. Non-zero exit on any failure.
The deploy guard has its own entrypoint: ``python -m office_connect.ops.deploy_guard``.
"""

import argparse
import json
import sys
from pathlib import Path

from office_connect.core.config import get_settings
from office_connect.ops.backup import create_backup, latest_backup, prune_old_backups
from office_connect.ops.restore_drill import run_backup_and_drill, run_restore_drill


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="office_connect.ops")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("backup", help="pg_dump -Fc + prune")
    drill = sub.add_parser("restore-drill", help="restore a dump into a scratch DB + verify")
    drill.add_argument("--file", default="latest", help="'latest' or a dump path")
    sub.add_parser("backup-and-drill", help="backup then restore-drill (the proof)")
    scan = sub.add_parser(
        "scan-pending", help="scan any pending/error attachments (Increment 4)"
    )
    scan.add_argument("--limit", type=int, default=100)
    args = parser.parse_args(argv)

    settings = get_settings()

    if args.command == "backup":
        dump = create_backup(settings)
        pruned = prune_old_backups(settings.backup_retention, settings)
        result = {"dump": str(dump), "pruned": [str(p) for p in pruned]}
    elif args.command == "restore-drill":
        if args.file == "latest":
            dump = latest_backup(settings)
            if dump is None:
                print("no backups found — run 'backup' first", file=sys.stderr)
                return 1
        else:
            dump = Path(args.file)
            if not dump.is_file():
                print(f"dump not found: {dump}", file=sys.stderr)
                return 1
        result = run_restore_drill(dump, settings)
    elif args.command == "scan-pending":
        from office_connect.ops.attachments_tasks import scan_pending_attachments

        result = scan_pending_attachments.run(limit=args.limit)
    else:  # backup-and-drill
        result = run_backup_and_drill(settings)

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
