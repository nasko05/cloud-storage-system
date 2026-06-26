"""Application configuration loaded from the environment.

All tunables live here so the rest of the codebase never reaches into
``os.environ`` directly. Values are read once at import time.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DRIVE_", env_file=".env", extra="ignore")

    # Storage / database
    database_url: str = "sqlite:///./data/app.db"
    storage_dir: Path = Path("./data/blobs")
    run_migrations: bool = True

    # Security
    secret_key: str = "change-me-in-production"
    access_token_expiry_minutes: int = 60 * 24
    signed_url_expiry_seconds: int = 3600
    pbkdf2_iterations: int = 260_000

    # Login brute-force protection
    login_max_attempts: int = 5
    login_window_seconds: int = 300
    login_lockout_seconds: int = 900

    # WebAuthn / passkeys. By default the RP ID and origin are derived from each
    # incoming request (the browser's Origin/Referer), so passkeys work on
    # whatever domain the app is actually served from without configuration.
    # Set these only to pin them explicitly — e.g. when the frontend lives on a
    # different host than the API, or behind a proxy that rewrites Origin. RP ID
    # is the registrable domain (no scheme/port/path); origin is the full
    # scheme://host:port, comma-split so several can be allowed at once.
    webauthn_rp_id: str = ""
    webauthn_rp_name: str = "Personal Drive"
    webauthn_origin: Annotated[list[str], NoDecode] = []

    # Per-user storage quota in bytes (0 = unlimited)
    user_quota_bytes: int = 0

    # Backups
    backup_dir: Path = Path("./data/backups")
    backup_interval_hours: int = 24
    backup_retention: int = 10
    maintenance_interval_minutes: int = 60
    enable_scheduler: bool = True
    # Abandoned ("pending", never-finalized) uploads older than this are purged
    # by the housekeeping sweep. 0 disables auto-cleanup. On demand via the CLI:
    # `python -m app.cli cleanup-partial-uploads`.
    partial_upload_max_age_hours: int = 24

    # Antivirus (ClamAV over TCP); disabled by default
    clamav_enabled: bool = False
    clamav_host: str = "clamav"
    clamav_port: int = 3310

    # Domain rules
    share_expiry_days: int = 30
    idempotency_ttl_seconds: int = 86_400
    archive_job_ttl_days: int = 1
    max_archive_files: int = 1000
    max_archive_total_bytes: int = 2 * 1024 * 1024 * 1024  # 2 GiB
    max_filename_length: int = 255

    # Behaviour
    require_email_confirmation: bool = False
    # NoDecode stops pydantic-settings from JSON-decoding the env value so a
    # plain comma-separated string (e.g. "*" or "https://a.com,https://b.com")
    # is accepted and split by the validator below.
    cors_allow_origins: Annotated[list[str], NoDecode] = ["*"]
    serve_frontend: bool = True
    frontend_dir: Path = Path("./static")

    @field_validator("cors_allow_origins", "webauthn_origin", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
