"""B2: the session Redis URL derives db 4 in CORE, without importing ops.

The import-linter contract (core ↛ ops) is enforced separately; this proves the
core-local ``redis_db_url`` twin is behaviourally identical to the ops helper so
duplicating it is safe.
"""

from urllib.parse import urlsplit

from office_connect.core.config import get_settings, redis_db_url


def test_resolved_session_redis_url_is_db_4():
    assert urlsplit(get_settings().resolved_session_redis_url).path == "/4"


def test_redis_db_url_matches_ops_twin():
    from office_connect.ops.dsn import redis_url_with_db

    url = "redis://user:pw@host:6379/0"
    assert redis_db_url(url, 4) == redis_url_with_db(url, 4)


def test_explicit_override_wins(monkeypatch):
    from office_connect.core import config

    config.get_settings.cache_clear()
    monkeypatch.setenv("SESSION_REDIS_URL", "redis://elsewhere:6379/9")
    try:
        assert config.get_settings().resolved_session_redis_url == "redis://elsewhere:6379/9"
    finally:
        config.get_settings.cache_clear()
