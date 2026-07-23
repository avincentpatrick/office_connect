"""Security primitives for identity & access (Stage B / Phase 2).

Pure, dependency-light helpers shared by the identity increment (break-glass
admin provisioning) and the B2 login flow. No DB, no request context here — this
package is the low-level toolbox the auth service composes.
"""

from office_connect.core.security.password import (
    generate_temp_password,
    hash_password,
    needs_rehash,
    verify_password,
)

__all__ = [
    "generate_temp_password",
    "hash_password",
    "needs_rehash",
    "verify_password",
]
