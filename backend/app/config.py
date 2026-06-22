"""Application configuration loaded from the environment.

All tunables live here so the rest of the codebase never reaches into
``os.environ`` directly. Values are read once at import time.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DRIVE_", env_file=".env", extra="ignore")

    # Storage / database
    database_url: str = "sqlite:///./data/app.db"
    storage_dir: Path = Path("./data/blobs")

    # Security
    secret_key: str = "change-me-in-production"
    access_token_expiry_minutes: int = 60 * 24
    signed_url_expiry_seconds: int = 3600
    pbkdf2_iterations: int = 260_000

    # Domain rules
    share_expiry_days: int = 30
    idempotency_ttl_seconds: int = 86_400
    archive_job_ttl_days: int = 1
    max_archive_files: int = 1000
    max_archive_total_bytes: int = 2 * 1024 * 1024 * 1024  # 2 GiB
    max_filename_length: int = 255

    # Behaviour
    require_email_confirmation: bool = False
    cors_allow_origins: list[str] = ["*"]
    serve_frontend: bool = True
    frontend_dir: Path = Path("./static")

    @field_validator("cors_allow_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
