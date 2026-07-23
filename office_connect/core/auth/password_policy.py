"""NIST SP 800-63B-4 password policy (auth-rbac-onprem.md).

House minimum **12** characters, max **128** (bounds Argon2 CPU); all Unicode,
spaces, and paste allowed. **No composition rules, no periodic expiration** —
passwords change only on evidence of compromise. A **blocklist** check (bundled
top-100k, no cloud) rejects common passwords, and a context-specific check rejects
passwords that embed the user's email local-part or username (NIST §3.1.1.2).

**Documented deviation** (master-plan §5 corrections ledger): the reference source
system specified "min 8, >=1 letter + 1 number". Office-Connect follows NIST
800-63B-4 §3.1.1 instead — length 12+ and a blocklist, no composition, no rotation.
"""

from __future__ import annotations

import unicodedata

from office_connect.core.config import get_settings
from office_connect.core.security.blocklists import is_blocklisted


def normalize_password(password: str) -> str:
    """NFKC-normalize before hashing/verifying (NIST §3.1.1.2 wants consistent
    normalization). Applied at every hash/verify call site so a passphrase typed
    with combining characters verifies stably; ``core/security/password.py`` stays
    byte-for-byte unchanged (it hashes whatever bytes it is given)."""
    return unicodedata.normalize("NFKC", password)


class PasswordPolicyError(ValueError):
    """Carries the list of stable machine codes for the envelope ``details``."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


def validate_password(
    password: str, *, email: str | None = None, username: str | None = None
) -> None:
    """Raise ``PasswordPolicyError`` (all failures collected) if non-compliant."""
    settings = get_settings()
    normalized = normalize_password(password)
    errors: list[str] = []
    if len(normalized) < settings.pwd_min_length:
        errors.append("too_short")
    if len(normalized) > settings.pwd_max_length:
        errors.append("too_long")
    if is_blocklisted(normalized):
        errors.append("blocklisted")
    if _contains_identifier(normalized, email, username):
        errors.append("contains_identifier")
    if errors:
        raise PasswordPolicyError(errors)


def _contains_identifier(
    password: str, email: str | None, username: str | None
) -> bool:
    pw = password.casefold()
    candidates: list[str] = []
    if email:
        candidates.append(email.split("@", 1)[0])
    if username:
        candidates.append(username)
    for candidate in candidates:
        c = candidate.strip().casefold()
        if len(c) >= 4 and c in pw:
            return True
    return False
