"""Portable database export / import.

A single JSON document covering every table, so it round-trips between SQLite and
PostgreSQL. Used by both the management CLI and the backup bundler.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import DateTime, delete, insert, inspect

from .database import SessionLocal, init_db
from .models import ArchiveJob, File, Folder, IdempotencyRecord, PublicLink, Share, User

EXPORT_VERSION = 1

# Insert order (parents before children); deletes happen in reverse.
MODELS = [User, Folder, File, Share, PublicLink, ArchiveJob, IdempotencyRecord]


def _serialize(value: object) -> object:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat()
    return value


def _deserialize(value: object, is_datetime: bool) -> object:
    if value is None or not is_datetime:
        return value
    text = str(value).replace("Z", "+00:00")
    return datetime.fromisoformat(text)


def export_to_dict() -> dict:
    db = SessionLocal()
    try:
        tables: dict[str, list[dict]] = {}
        for model in MODELS:
            columns = [c.key for c in inspect(model).columns]
            rows = db.execute(model.__table__.select()).mappings().all()
            tables[model.__tablename__] = [
                {col: _serialize(row[col]) for col in columns} for row in rows
            ]
        return {"version": EXPORT_VERSION, "tables": tables}
    finally:
        db.close()


def import_from_dict(payload: dict, replace: bool) -> int:
    if payload.get("version") != EXPORT_VERSION:
        raise ValueError(f"Unsupported export version: {payload.get('version')}")

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
            datetime_cols = {c.key for c in inspect(model).columns if isinstance(c.type, DateTime)}
            mapped = [
                {key: _deserialize(value, key in datetime_cols) for key, value in row.items()}
                for row in rows
            ]
            db.execute(insert(model), mapped)
        db.commit()
        return sum(len(tables.get(m.__tablename__, [])) for m in MODELS)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def export_db(output: str) -> int:
    payload = export_to_dict()
    with open(output, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    return sum(len(v) for v in payload["tables"].values())


def import_db(input_path: str, replace: bool) -> int:
    with open(input_path, encoding="utf-8") as handle:
        payload = json.load(handle)
    return import_from_dict(payload, replace)
