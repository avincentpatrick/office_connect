"""Session timeout + role-tier policy — pure math, no IO (auth-rbac-onprem.md).

Absolute lifetime 12h; idle timeout 30 min for privileged roles (system_admin /
approver / auditor — the money-approving and audit-reading surfaces) vs 60 min
for ordinary staff; a short reauth window gates high-impact actions (own-password
change). Timeouts are enforced **server-side** on every request via the session's
``created_at`` / ``last_seen_at`` — the cookie is never trusted for lifetime.
"""

from collections.abc import Iterable
from datetime import datetime, timedelta

from office_connect.core.config import Settings
from office_connect.core.time import utc_now

# Roles that get the tighter 30-min idle tier. auditor is included: it reads the
# audit trail (sensitive personal data), so it is treated as privileged.
PRIVILEGED_ROLE_CODES: frozenset[str] = frozenset(
    {"system_admin", "approver", "auditor"}
)


def is_privileged(role_codes: Iterable[str]) -> bool:
    return bool(PRIVILEGED_ROLE_CODES.intersection(role_codes))


def idle_tier_for(role_codes: Iterable[str]) -> str:
    """"privileged" (30-min idle) if the user holds any privileged role, else "staff"."""
    return "privileged" if is_privileged(role_codes) else "staff"


def idle_seconds_for(idle_tier: str, settings: Settings) -> int:
    return (
        settings.session_idle_privileged_seconds
        if idle_tier == "privileged"
        else settings.session_idle_staff_seconds
    )


def absolute_expires_at(created_at: datetime, settings: Settings) -> datetime:
    return created_at + timedelta(seconds=settings.session_absolute_seconds)


def expiry_reason(
    *,
    created_at: datetime,
    last_seen_at: datetime,
    idle_tier: str,
    settings: Settings,
    now: datetime | None = None,
) -> str | None:
    """None if the session is still valid, else "absolute" or "idle"."""
    now = now or utc_now()
    if now >= created_at + timedelta(seconds=settings.session_absolute_seconds):
        return "absolute"
    if now >= last_seen_at + timedelta(seconds=idle_seconds_for(idle_tier, settings)):
        return "idle"
    return None


def reauth_required(
    last_auth_at: datetime, *, settings: Settings, now: datetime | None = None
) -> bool:
    """True when the last credential proof is older than the reauth window."""
    now = now or utc_now()
    return now >= last_auth_at + timedelta(seconds=settings.session_reauth_seconds)
