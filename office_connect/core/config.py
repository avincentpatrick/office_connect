"""Application settings, loaded from environment / .env (pydantic-settings v2)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "Office-Connect"
    app_env: str = "local"
    app_port: int = 8001

    # Public origin the app is served from (Day-1 #10 — uvicorn runs with
    # --proxy-headers so links/redirects are correct behind a reverse proxy).
    base_url: str = "http://localhost:8001"

    # Runtime DB role (oc_app): SELECT/INSERT/UPDATE only — no DELETE anywhere,
    # no UPDATE on append-only tables (docs/standards/database-standards.md §8).
    database_url: str = "postgresql+asyncpg://oc_app:oc_app_pw@db:5432/office_connect"
    # Owner/migration role (oc_dev) — Alembic and privileged fixtures only.
    migration_database_url: str = (
        "postgresql+asyncpg://oc_dev:oc_dev_pw@db:5432/office_connect"
    )

    redis_url: str = "redis://redis:6379/0"

    session_secret: str = "dev-only-change-me"

    # --- Phase 0 Increment 3 placeholders (drivers land later) ---
    google_credentials_path: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
