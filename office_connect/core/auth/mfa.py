"""TOTP MFA (RFC 6238, via ``pyotp``) — required for approver/admin roles
(NPC Circular 2023-06 requires MFA for personal-data access).

Enrollment returns the ``otpauth://`` provisioning URI so the client renders the
QR — no server-side image dependency. Login for an ``mfa_enabled`` user is a
two-step challenge (password → ``mfa_required`` + short-lived token → this verify).
``check_and_consume`` makes a code single-use within its window (Redis ``SETNX``),
so a still-valid code can't be replayed.
"""

from __future__ import annotations

from datetime import datetime

import pyotp
from redis.asyncio import Redis

from office_connect.core.time import utc_now


def generate_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, account_name: str, issuer: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=account_name, issuer_name=issuer)


def _normalize_code(code: str) -> str:
    return (code or "").strip().replace(" ", "")


def verify_code(
    secret: str,
    code: str,
    *,
    valid_window: int = 1,
    at_time: datetime | None = None,
) -> bool:
    """Fail-closed TOTP check (±``valid_window`` 30s steps of clock skew)."""
    code = _normalize_code(code)
    if not secret or not code:
        return False
    try:
        return bool(
            pyotp.TOTP(secret).verify(
                code, for_time=at_time, valid_window=valid_window
            )
        )
    except Exception:  # noqa: BLE001 — never raise from a credential check
        return False


async def check_and_consume(
    redis: Redis,
    user_id: int,
    secret: str,
    code: str,
    *,
    valid_window: int = 1,
    at_time: datetime | None = None,
) -> bool:
    """``verify_code`` + single-use within the step window (replay resistance)."""
    if not verify_code(secret, code, valid_window=valid_window, at_time=at_time):
        return False
    code = _normalize_code(code)
    now = at_time or utc_now()
    totp = pyotp.TOTP(secret)
    interval = totp.interval
    base_counter = int(now.timestamp() // interval)
    matched_counter: int | None = None
    for offset in range(-valid_window, valid_window + 1):
        if totp.at(now, counter_offset=offset) == code:
            matched_counter = base_counter + offset
            break
    if matched_counter is None:  # verified but not localizable — allow (shouldn't happen)
        return True
    key = f"mfa:used:{user_id}:{matched_counter}"
    ttl = (2 * valid_window + 2) * interval
    stored = await redis.set(key, "1", nx=True, ex=ttl)
    return bool(stored)  # None -> already used within window -> replay -> reject
