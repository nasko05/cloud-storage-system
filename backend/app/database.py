"""SQLAlchemy engine, session factory and declarative base.

The engine is built from ``settings.database_url`` so the same code runs
against PostgreSQL (production / container) and SQLite (tests, local dev).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

logger = logging.getLogger("database")


class Base(DeclarativeBase):
    pass


def _engine_kwargs(url: str) -> dict:
    if url.startswith("sqlite"):
        # check_same_thread=False lets the background archive worker share the
        # in-memory/file database with the request threads.
        return {"connect_args": {"check_same_thread": False}, "future": True}
    return {"pool_pre_ping": True, "future": True}


engine = create_engine(settings.database_url, **_engine_kwargs(settings.database_url))
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)

if settings.database_url.startswith("sqlite"):
    # SQLite disables foreign keys by default; enable them so behaviour (and
    # tests) match PostgreSQL, which always enforces them.
    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def _upgrade_to_head() -> None:
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    ini_path = Path(__file__).resolve().parent.parent / "alembic.ini"
    cfg = Config(str(ini_path))
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(cfg, "head")


def init_db(retries: int = 15, delay: float = 2.0) -> None:
    """Bring the schema up to date, waiting for the database to be reachable.

    In production (``run_migrations=True``) this applies Alembic migrations; in
    tests it creates tables directly from the models. The app container can start
    before PostgreSQL is ready, so the initial connection is retried.
    """
    from . import models  # noqa: F401  (register mappers)

    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            if settings.run_migrations:
                _upgrade_to_head()
            else:
                Base.metadata.create_all(bind=engine)
            return
        except OperationalError as error:
            last_error = error
            logger.warning("database not ready (attempt %s/%s); retrying...", attempt, retries)
            time.sleep(delay)
    raise RuntimeError("Database did not become ready in time") from last_error


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a scoped session with commit/rollback."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
