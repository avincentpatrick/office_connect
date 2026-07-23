"""Credential verifier selection — the break-glass / future-LDAP branch point.

B2 has no LDAP backend, so every account verifies locally. The branch is written
and documented now so the intent is explicit: a **break-glass** account
(``is_break_glass``) ALWAYS verifies locally — checked ABOVE any
``auth_source == "ldap"`` routing — so a domain-controller / feature-flag-store
outage can never lock out every admin. Break-glass is still subject to password +
MFA; it is only exempt from the (future) directory backend.
"""

from __future__ import annotations

from office_connect.core.models import User
from office_connect.core.security import verify_password


class LocalPasswordVerifier:
    """Verify against the Argon2id ``core_users.password_hash`` (fail-closed)."""

    def verify(self, user: User, password: str) -> bool:
        return verify_password(password, user.password_hash or "")


def select_verifier(user: User, *, ldap_enabled: bool = False) -> LocalPasswordVerifier:
    # Break-glass is ALWAYS local — never routed to LDAP, even once it lands.
    if user.is_break_glass:
        return LocalPasswordVerifier()
    if ldap_enabled and user.auth_source == "ldap":
        raise NotImplementedError(
            "the LDAP verifier arrives in a later increment; auth_source='ldap' "
            "accounts cannot log in yet"
        )
    return LocalPasswordVerifier()
