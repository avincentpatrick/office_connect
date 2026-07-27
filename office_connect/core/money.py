"""Platform money convention — non-configurable, parallel to ``core/time.py``.

Philippine Peso, ``numeric(12, 2)``, **all arithmetic server-side** — the UI
displays, never computes (docs/standards/database-standards.md §10). Rounding is
``ROUND_HALF_UP`` to the centavo: the mode an accountant re-performing the
computation by hand arrives at (banker's rounding would produce audit
mismatches). Inside JSONB, money is serialized as a 2-dp string (``"1234.50"``),
never a float — JSON numbers round-trip through binary floats.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def to_money(value: Decimal | int | str) -> Decimal:
    """Quantize to 0.01 ``ROUND_HALF_UP`` — the only sanctioned money rounding."""
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def money_str(value: Decimal | int | str) -> str:
    """Canonical JSONB serialization of a money value: ``"1234.50"``."""
    return str(to_money(value))
