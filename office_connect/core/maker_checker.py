"""Maker-checker / segregation of duties (Stage B / Increment 3).

COA 92-389 + NGICS require that the person who prepares/certifies a disbursement
voucher is not the person who approves it, and that the DV's Boxes A / B / C carry
*distinct* signatories. This is the reusable, dependency-free primitive that
enforces "no self-approval; distinct approver per box" — the Stage-C reimbursement
approval flow calls it with the concrete DV-box actor ids.

B3 ships the pure check + tests; the DB-level constraint (an exclusion/unique
over the approval table's box columns) lands with that table in Stage C — there is
no approval table to constrain yet.
"""

from __future__ import annotations

from collections.abc import Sequence

from office_connect.core.api.errors import APIError

_CODE = "segregation_of_duties"


def assert_segregation(*, maker_id: int, checker_ids: Sequence[int]) -> None:
    """Raise ``APIError(409, "segregation_of_duties")`` if the maker also appears
    as a checker, or if any two checker slots (DV Boxes A/B/C) share one person.
    Passes silently when every party is distinct."""
    checkers = list(checker_ids)
    if maker_id in checkers:
        raise APIError(
            409,
            _CODE,
            "The person who prepared this cannot also approve it.",
        )
    seen: set[int] = set()
    for cid in checkers:
        if cid in seen:
            raise APIError(
                409,
                _CODE,
                "Each approval step must be signed by a distinct approver.",
            )
        seen.add(cid)
