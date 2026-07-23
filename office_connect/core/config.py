"""Application settings, loaded from environment / .env (pydantic-settings v2)."""

from functools import lru_cache
from urllib.parse import urlsplit, urlunsplit

from pydantic_settings import BaseSettings, SettingsConfigDict


def redis_db_url(base_url: str, db: int) -> str:
    """Point a ``redis://`` URL at a specific logical DB, keeping auth/host.

    A core-local twin of ``office_connect.ops.dsn.redis_url_with_db`` — duplicated
    ON PURPOSE so ``core`` never imports ``ops`` (the import-linter contract that
    the B2 resume brief's "derive via ops/dsn" instruction would have broken).
    Keep the two behaviourally identical.
    """
    parts = urlsplit(base_url)
    return urlunsplit(parts._replace(path=f"/{db}"))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "Office-Connect"
    app_env: str = "local"
    app_port: int = 8001

    # --- Observability (Increment 4) ---
    # Structured JSON logs with request IDs (core/logging.py). Set LOG_JSON=false
    # for human-readable dev logs. Self-hosted error tracker (GlitchTip) is
    # fail-safe optional: no SENTRY_DSN = no tracking, never a startup failure.
    log_level: str = "INFO"
    log_json: bool = True
    sentry_dsn: str | None = None

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

    # --- Auth / sessions (Stage B / Increment 2) ---
    # Server-side sessions live on a DEDICATED Redis logical DB (db 4) so the
    # keyspace never collides with the config cache (db 0), the Celery broker /
    # results (db 1 / 2), or GlitchTip (db 3, observability profile). Set
    # SESSION_REDIS_URL to override the whole URL; else it derives from redis_url.
    session_redis_db: int = 4
    session_redis_url: str | None = None
    # Opaque session-id cookie. HttpOnly + SameSite=Lax are always on; Secure is
    # resolved from app_env unless forced (SESSION_COOKIE_SECURE=false for local
    # http dev). Path narrows the cookie to the API surface.
    session_cookie_name: str = "oc_session"
    session_cookie_secure: bool | None = None  # None -> True unless app_env=="local"
    session_cookie_path: str = "/api"
    session_cookie_samesite: str = "lax"
    session_cookie_domain: str | None = None
    # Server-enforced lifetimes (auth-rbac-onprem.md): 12h absolute; idle 30 min
    # for privileged roles / 60 min for staff; reauth window for high-impact acts.
    session_absolute_seconds: int = 12 * 3600
    session_idle_privileged_seconds: int = 30 * 60
    session_idle_staff_seconds: int = 60 * 60
    session_reauth_seconds: int = 5 * 60
    session_max_concurrent: int = 3
    session_cap_policy: str = "evict_oldest"  # or "reject"
    # Throttle-not-lockout: per-account + per-IP counters, exponential backoff
    # after N consecutive failures (never a permanent lock), reset on success.
    throttle_threshold: int = 5
    throttle_backoff_base_seconds: int = 1
    throttle_backoff_ceiling_seconds: int = 300
    throttle_window_seconds: int = 900
    # Custom-header CSRF (SameSite=Lax floor + a header the SPA fetch wrapper sets).
    csrf_header_name: str = "X-Requested-With"
    # NIST 800-63B-4 password policy (no composition, no rotation; blocklist).
    pwd_min_length: int = 12
    pwd_max_length: int = 128
    # TOTP MFA (RFC 6238) — required for these role codes (NPC Circular 2023-06).
    mfa_issuer: str = "Office-Connect"
    mfa_valid_window: int = 1
    mfa_required_role_codes: frozenset[str] = frozenset({"system_admin", "approver"})

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

    # --- Notifications outbox (Increment 4) ---
    # 'inline' = persist + dispatch synchronously in-process (CLI/tests/scripts,
    # no worker needed — the default). 'celery' = the running app enqueues the
    # dispatch to the worker after the outbox row commits.
    notifications_dispatch: str = "inline"
    notifications_max_attempts: int = 5
    notifications_retry_base_seconds: int = 60
    notifications_retry_max_seconds: int = 3600

    # --- Attachments + malware scan (Increment 4) ---
    # Upper bound on a single upload's byte size (default 20 MiB). The service
    # rejects anything larger before it touches storage.
    attachment_max_bytes: int = 20 * 1024 * 1024
    # Scanner selection: None = auto ('clamav' when clamav_host is set, else
    # 'null'). The NullScanner is fail-closed — it denies in production (no
    # verdict = untrusted) and passes in dev/test so the pipeline round-trips
    # without a 3 GB ClamAV daemon. ClamAV is opt-in via the compose profile.
    attachment_scanner: str | None = None
    clamav_host: str | None = None
    clamav_port: int = 3310

    @property
    def resolved_session_redis_url(self) -> str:
        """The session store's Redis URL — explicit override, else redis_url@db."""
        return self.session_redis_url or redis_db_url(
            self.redis_url, self.session_redis_db
        )

    @property
    def resolved_cookie_secure(self) -> bool:
        """Secure cookie flag — on everywhere except local http dev, unless forced."""
        if self.session_cookie_secure is None:
            return self.app_env != "local"
        return self.session_cookie_secure


@lru_cache
def get_settings() -> Settings:
    return Settings()
