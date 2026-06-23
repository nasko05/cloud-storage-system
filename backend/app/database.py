"""SQLAlchemy engine, session factory and declarative base.

The engine is built from ``settings.database_url`` so the same code runs
against PostgreSQL (production / container) and SQLite (tests, local dev).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator

from sqlalchemy import create_engine
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


def init_db(retries: int = 15, delay: float = 2.0) -> None:
    """Create all tables, waiting for the database to accept connections.

    The app container can start before the PostgreSQL container is ready, so we
    retry the initial connection a handful of times before giving up.
    """
    from . import models  # noqa: F401  (register mappers)

    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
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
