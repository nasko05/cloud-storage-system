"""Relational data model.

This replaces the DynamoDB single-table design with normalised tables. The
``isShared`` / ``hasPublicLink`` flags that were previously denormalised
counters are now derived at query time via existence checks, which removes a
whole class of counter-drift bugs.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from .database import Base

ROOT_FOLDER_ID = "root"


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    # Naive UTC — see app.utils for the rationale.
    return datetime.utcnow()


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_confirmed: Mapped[bool] = mapped_column(default=False, nullable=False)
    confirmation_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Folder(Base):
    __tablename__ = "folders"
    __table_args__ = (Index("ix_folders_owner_parent", "owner_id", "parent_folder_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    owner_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_folder_id: Mapped[str] = mapped_column(String(64), default=ROOT_FOLDER_ID, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class File(Base):
    __tablename__ = "files"
    __table_args__ = (Index("ix_files_owner_parent", "owner_id", "parent_folder_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    owner_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), nullable=False)
    owner_email: Mapped[str] = mapped_column(String(320), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_folder_id: Mapped[str] = mapped_column(String(64), default=ROOT_FOLDER_ID, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), default="application/octet-stream")
    size: Mapped[int] = mapped_column(BigInteger, default=0)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    shares: Mapped[list["Share"]] = relationship(
        back_populates="file", cascade="all, delete-orphan", passive_deletes=True
    )
    public_links: Mapped[list["PublicLink"]] = relationship(
        back_populates="file", cascade="all, delete-orphan", passive_deletes=True
    )


class Share(Base):
    __tablename__ = "shares"
    __table_args__ = (
        UniqueConstraint("file_id", "principal_type", "principal_value", name="uq_share_principal"),
        Index("ix_shares_principal", "principal_type", "principal_value"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    file_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("files.id", ondelete="CASCADE"), nullable=False
    )
    principal_type: Mapped[str] = mapped_column(String(16), nullable=False)
    principal_value: Mapped[str] = mapped_column(String(320), nullable=False)
    principal_display: Mapped[str] = mapped_column(String(320), nullable=False)
    permission: Mapped[str] = mapped_column(String(16), default="read")
    shared_by: Mapped[str] = mapped_column(String(64), nullable=False)
    shared_by_email: Mapped[str] = mapped_column(String(320), nullable=False)
    shared_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    file: Mapped["File"] = relationship(back_populates="shares")


class PublicLink(Base):
    __tablename__ = "public_links"

    token: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    file_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("files.id", ondelete="CASCADE"), nullable=False
    )
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False)
    owner_email: Mapped[str] = mapped_column(String(320), nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    download_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    file: Mapped["File"] = relationship(back_populates="public_links")


class ArchiveJob(Base):
    __tablename__ = "archive_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    requested_file_ids: Mapped[list] = mapped_column(JSON, default=list)
    requested_folder_ids: Mapped[list] = mapped_column(JSON, default=list)
    zip_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    file_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    response_body: Mapped[dict] = mapped_column(JSON, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
