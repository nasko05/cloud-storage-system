"""Management CLI: portable database export / import for migrations.

The export is a single JSON document covering every table, so it round-trips
between SQLite and PostgreSQL. File *bytes* live on the storage volume and are
migrated by copying that directory (see the VPS guide); this tool moves the
metadata.

Usage::

    python -m app.cli export --output backup.json
    python -m app.cli import --input backup.json [--replace]
    python -m app.cli init
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from sqlalchemy import DateTime, delete, inspect

from .database import SessionLocal, init_db
from .models import ArchiveJob, File, Folder, IdempotencyRecord, PublicLink, Share, User

EXPORT_VERSION = 1

# Children before parents on import is handled by ordering; export order is
# parent-first, import inserts in this order and deletes in reverse.
MODELS = [User, Folder, File, Share, PublicLink, ArchiveJob, IdempotencyRecord]


def _serialize(value: object) -> object:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    return value


def _deserialize(value: object, is_datetime: bool) -> object:
    if value is None or not is_datetime:
        return value
    text = str(value).replace("Z", "+00:00")
    return datetime.fromisoformat(text)


def export_db(output: str) -> None:
    db = SessionLocal()
    try:
        tables: dict[str, list[dict]] = {}
        for model in MODELS:
            columns = [c.key for c in inspect(model).columns]
            rows = db.execute(inspect(model).local_table.select()).mappings().all()
            tables[model.__tablename__] = [
                {col: _serialize(row[col]) for col in columns} for row in rows
            ]
        payload = {"version": EXPORT_VERSION, "tables": tables}
        with open(output, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        total = sum(len(v) for v in tables.values())
        print(f"Exported {total} rows across {len(tables)} tables to {output}")
    finally:
        db.close()


def import_db(input_path: str, replace: bool) -> None:
    with open(input_path, encoding="utf-8") as handle:
        payload = json.load(handle)
    if payload.get("version") != EXPORT_VERSION:
        raise SystemExit(f"Unsupported export version: {payload.get('version')}")

    init_db()
    tables = payload.get("tables", {})
    db = SessionLocal()
    try:
        if replace:
            for model in reversed(MODELS):
                db.execute(delete(model))

        for model in MODELS:
            rows = tables.get(model.__tablename__, [])
            if not rows:
                continue
            datetime_cols = {
                c.key for c in inspect(model).columns if isinstance(c.type, DateTime)
            }
            mapped = [
                {key: _deserialize(value, key in datetime_cols) for key, value in row.items()}
                for row in rows
            ]
            db.execute(inspect(model).local_table.insert(), mapped)
        db.commit()
        total = sum(len(tables.get(m.__tablename__, [])) for m in MODELS)
        print(f"Imported {total} rows from {input_path}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli", description="Database management commands")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Create database tables if missing")

    export_cmd = sub.add_parser("export", help="Export all tables to JSON")
    export_cmd.add_argument("--output", "-o", required=True)

    import_cmd = sub.add_parser("import", help="Import all tables from JSON")
    import_cmd.add_argument("--input", "-i", required=True)
    import_cmd.add_argument(
        "--replace", action="store_true", help="Delete existing rows before importing"
    )

    args = parser.parse_args(argv)
    if args.command == "init":
        init_db()
        print("Database initialised")
    elif args.command == "export":
        export_db(args.output)
    elif args.command == "import":
        import_db(args.input, args.replace)
    return 0


if __name__ == "__main__":
    sys.exit(main())
