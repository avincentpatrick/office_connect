"""URL helpers shared by the ops subsystem.

- ``libpq_env`` turns a SQLAlchemy async URL into the ``PG*`` environment the
  Postgres CLI tools (pg_dump/pg_restore/createdb/dropdb) read, so no password
  ever appears on a command line.
- ``swap_database`` / ``database_name`` support pointing an async engine at the
  scratch DB during the restore drill.
- ``redis_url_with_db`` derives the Celery broker/result URLs from ``redis_url``
  on a different logical DB than the app config cache.
"""

import os
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy.engine import make_url


def libpq_env(
    url_str: str,
    *,
    database: str | None = None,
    base_env: dict[str, str] | None = None,
) -> dict[str, str]:
    """Build a libpq ``PG*`` env dict from a SQLAlchemy URL (driver stripped).

    ``database`` overrides the DB in the URL — used to target the maintenance
    DB ``postgres`` for createdb/dropdb, or a scratch DB for pg_restore.
    """
    url = make_url(url_str)
    env = dict(os.environ if base_env is None else base_env)
    env["PGHOST"] = url.host or "localhost"
    env["PGPORT"] = str(url.port or 5432)
    if url.username:
        env["PGUSER"] = url.username
    if url.password is not None:
        env["PGPASSWORD"] = url.password
    env["PGDATABASE"] = database or url.database or ""
    return env


def swap_database(url_str: str, new_db: str) -> str:
    """Return the URL with its database replaced (keeps driver + credentials).

    ``render_as_string(hide_password=False)`` is required — SQLAlchemy's
    ``str(URL)`` masks the password as ``***``, which would make asyncpg auth
    fail on the rebuilt URL.
    """
    return make_url(url_str).set(database=new_db).render_as_string(hide_password=False)


def database_name(url_str: str) -> str | None:
    return make_url(url_str).database


def redis_url_with_db(url_str: str, db: int) -> str:
    """``redis://host:port/0`` -> ``redis://host:port/<db>`` (keeps auth/host)."""
    parts = urlsplit(url_str)
    return urlunsplit(parts._replace(path=f"/{db}"))
