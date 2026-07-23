"""Password hashing — Argon2id (OWASP first-choice, memory-hard).

Stage B (Phase 2), per docs/research/round1/auth-rbac-onprem.md. The single
hasher for local-auth credentials: the break-glass admin promotion (Increment
B1) and the B2 login flow both go through here — never two hashers, never a
per-caller cost.

Parameters (recorded in docs/standards/tech-stack.md, standing rule 9) follow
OWASP Password Storage / RFC 9106's second option, sized for an on-prem server:
19 MiB memory, 2 iterations, 1 lane. A stored hash is a self-describing PHC
string, so raising the cost later is safe — ``needs_rehash`` flags old hashes to
be re-hashed transparently on the owner's next successful login.

Verification is fail-closed: any mismatch or malformed hash returns ``False``,
never raises. Never log the password, the hash, or the reason for a mismatch.
"""

from __future__ import annotations

import secrets

from argon2 import PasswordHasher
from argon2 import exceptions as argon2_exceptions

# Argon2id by default (Type.ID). Cost recorded in tech-stack.md — bump together.
_hasher = PasswordHasher(
    time_cost=2,
    memory_cost=19 * 1024,  # KiB → 19 MiB
    parallelism=1,
)


def hash_password(password: str) -> str:
    """Return an Argon2id PHC-format hash for ``password``."""
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """True iff ``password`` matches ``password_hash``. Fail-closed: a wrong
    password OR a malformed/foreign hash string returns ``False``, never raises."""
    try:
        _hasher.verify(password_hash, password)
        return True
    except argon2_exceptions.VerificationError:
        return False
    except argon2_exceptions.InvalidHashError:
        return False


def needs_rehash(password_hash: str) -> bool:
    """True if the stored hash was produced with weaker params than current
    policy — re-hash on the next successful verify."""
    return _hasher.check_needs_rehash(password_hash)


def generate_temp_password(n_bytes: int = 18) -> str:
    """A strong URL-safe random password for an admin-provisioned account
    (must be changed on first login). 18 bytes → 24 base64url chars ≈ 144 bits."""
    return secrets.token_urlsafe(n_bytes)
