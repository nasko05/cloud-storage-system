"""Management CLI.

Database snapshots (portable JSON) and full backups (DB + file bytes).

Usage::

    python -m app.cli init
    python -m app.cli export --output backup.json
    python -m app.cli import --input backup.json [--replace]
    python -m app.cli backup [--output-dir DIR]
    python -m app.cli restore --input backup-YYYYmmdd-HHMMSS.tar.gz
    python -m app.cli verify-backup --input <bundle>
    python -m app.cli cleanup-partial-uploads [--older-than-hours N] [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import backup as backup_mod
from . import maintenance
from .config import settings
from .database import init_db
from .dbio import export_db, import_db


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli", description="Database & backup management")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Create database tables if missing")

    export_cmd = sub.add_parser("export", help="Export all tables to JSON")
    export_cmd.add_argument("--output", "-o", required=True)

    import_cmd = sub.add_parser("import", help="Import all tables from JSON")
    import_cmd.add_argument("--input", "-i", required=True)
    import_cmd.add_argument("--replace", action="store_true", help="Delete existing rows first")

    backup_cmd = sub.add_parser("backup", help="Create a full backup (DB + files)")
    backup_cmd.add_argument("--output-dir", "-d", default=None)

    restore_cmd = sub.add_parser("restore", help="Restore a full backup bundle")
    restore_cmd.add_argument("--input", "-i", required=True)
    restore_cmd.add_argument(
        "--merge", action="store_true", help="Merge instead of replacing existing rows"
    )

    verify_cmd = sub.add_parser("verify-backup", help="Verify a backup bundle checksum")
    verify_cmd.add_argument("--input", "-i", required=True)

    cleanup_cmd = sub.add_parser(
        "cleanup-partial-uploads",
        help="Delete never-finalized ('pending') uploads and their leftover bytes",
    )
    cleanup_cmd.add_argument(
        "--older-than-hours",
        type=int,
        default=settings.partial_upload_max_age_hours,
        help="Only remove pending uploads older than this many hours (default: %(default)s)",
    )
    cleanup_cmd.add_argument(
        "--dry-run", action="store_true", help="List what would be removed without deleting"
    )

    args = parser.parse_args(argv)

    if args.command == "init":
        init_db()
        print("Database initialised")
    elif args.command == "export":
        count = export_db(args.output)
        print(f"Exported {count} rows to {args.output}")
    elif args.command == "import":
        count = import_db(args.input, args.replace)
        print(f"Imported {count} rows from {args.input}")
    elif args.command == "backup":
        bundle = backup_mod.create_backup(Path(args.output_dir) if args.output_dir else None)
        print(f"Backup written to {bundle}")
    elif args.command == "restore":
        backup_mod.restore_backup(Path(args.input), replace=not args.merge)
        print(f"Restored from {args.input}")
    elif args.command == "verify-backup":
        ok = backup_mod.verify(Path(args.input))
        print("OK" if ok else "CORRUPT")
        return 0 if ok else 1
    elif args.command == "cleanup-partial-uploads":
        removed = maintenance.run_cleanup_partial_uploads(
            args.older_than_hours, dry_run=args.dry_run
        )
        for file_id, filename in removed:
            print(f"  {file_id}  {filename}")
        verb = "Would remove" if args.dry_run else "Removed"
        print(f"{verb} {len(removed)} partial upload(s) older than {args.older_than_hours}h")
    return 0


if __name__ == "__main__":
    sys.exit(main())
