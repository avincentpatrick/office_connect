"""The single reader of ``core_feature_flags``.

Extracted at Stage D-2 (rule 10). ``require_feature`` gates a *route*; the
calendar dispatcher gates a *source* (api-standards §9k) — two callers asking the
identical question, which is exactly the point at which the question stops being
inlined and becomes a function. Two readers of one flag eventually disagree, and
the visible form of that disagreement is a module that is off for its own routes
and on for its calendar rows.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.models import FeatureFlag


async def feature_enabled(session: AsyncSession, flag_key: str) -> bool:
    """True when ``flag_key`` is ON: a live row with ``enabled AND is_active``.

    **Fail-safe OFF.** A missing row is OFF, a soft-deleted row is OFF, and a
    retired row (``is_active=False``) is OFF even if ``enabled`` was left true —
    ``enabled`` is the flag's state, ``is_active`` retires the row, and a feature
    is on only if both (foundation.md §4).
    """
    row = (
        await session.execute(select(FeatureFlag).where(FeatureFlag.key == flag_key))
    ).scalar_one_or_none()
    return bool(row and row.enabled and row.is_active)


__all__ = ["feature_enabled"]
