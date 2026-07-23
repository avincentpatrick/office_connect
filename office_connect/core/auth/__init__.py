"""Authentication runtime (Stage B / Increment 2).

Cookie-based **server-side** sessions on Redis (db 4), Argon2id login, NIST
800-63B-4 password policy + blocklist, throttle-not-lockout, custom-header CSRF,
break-glass login, and TOTP MFA — built per ``docs/research/round1/auth-rbac-onprem.md``.

Everything here lives in ``core`` and imports only stdlib, ``redis``, and other
``core.*`` modules — never ``ops`` / ``modules`` / ``worker`` / ``main`` (the
import-linter contract). External clients (the session-Redis connection) are
injected via ``app.state``, so nothing here reaches back into the app layer.

Public names are re-exported at the bottom once every submodule is defined.
"""

from office_connect.core.auth.principal import Principal
from office_connect.core.auth.session_store import SessionRecord, SessionStore

__all__ = ["Principal", "SessionRecord", "SessionStore"]
