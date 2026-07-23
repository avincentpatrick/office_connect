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

    # --- Celery (Increment 2) ---
    # Broker/result backends default to a DIFFERENT logical Redis DB than the
    # app config cache (which uses redis_url db 0) so keyspaces never collide;
    # worker.py derives db 1 (broker) / db 2 (results) from redis_url when these
    # are unset. Override via CELERY_BROKER_URL / CELERY_RESULT_BACKEND.
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None

    # --- Backup / restore drill (Increment 2) ---
    # In-container directory the nightly pg_dump writes to (bind-mounted to the
    # host ./backups). Retention keeps the newest N dumps. The restore drill
    # creates/drops a scratch DB whose name starts with this prefix.
    backups_dir: str = "/app/backups"
    backup_retention: int = 7
    scratch_db_prefix: str = "office_connect_restore"

    session_secret: str = "dev-only-change-me"

    # --- Storage driver (Increment 3) ---
    # local = content-addressed volume store (prod default, on-prem posture,
    # master-plan §4 #3); gdrive = Google Drive (kept for tenants that want it).
    storage_driver: str = "local"
    # In-container dir the local driver writes to (bind-mounted to host ./storage).
    storage_dir: str = "/app/storage"
    # Google Drive target (a Shared Drive folder id); the driver verifies the
    # target lives on a Shared Drive before uploading.
    gdrive_folder_id: str | None = None

    # --- Email driver (Increment 3) ---
    # None = auto: 'smtp' when smtp_host is set, else 'log' (dev fail-safe that
    # logs instead of sending). Explicit values: 'smtp' | 'gmail' | 'log'.
    email_driver: str | None = None
    # Gmail API delegated sender (domain-wide delegation); falls back to smtp_from.
    gmail_sender: str | None = None

    # --- Google service-account credentials (storage + email; Increment 3) ---
    google_credentials_path: str | None = None

    # --- SMTP (Increment 3) ---
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
