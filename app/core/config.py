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

    database_url: str = "postgresql+asyncpg://oc_dev:oc_dev_pw@db:5432/office_connect"
    redis_url: str = "redis://redis:6379/0"

    session_secret: str = "dev-only-change-me"


@lru_cache
def get_settings() -> Settings:
    return Settings()
