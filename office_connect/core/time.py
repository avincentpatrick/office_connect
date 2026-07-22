"""Platform time convention (Day-1 #2, plan C-1) — non-configurable.

Store UTC ``timestamptz``, display Asia/Manila. Naive datetimes are forbidden
(docs/standards/database-standards.md §9); ``ensure_aware`` raises on them.
Reconcile with CSS-IS's proven ``tzutil.py`` when the Phase 1 migration lands.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

UTC = timezone.utc
MANILA = ZoneInfo("Asia/Manila")


def utc_now() -> datetime:
    """Aware current time in UTC — the only sanctioned "now"."""
    return datetime.now(UTC)


def ensure_aware(dt: datetime) -> datetime:
    """Reject naive datetimes; return the input unchanged if aware."""
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        raise ValueError(
            "Naive datetime forbidden - all datetimes must be timezone-aware "
            "(store UTC, display Asia/Manila)."
        )
    return dt


def to_utc(dt: datetime) -> datetime:
    """Normalize an aware datetime to UTC (storage form)."""
    return ensure_aware(dt).astimezone(UTC)


def to_manila(dt: datetime) -> datetime:
    """Convert an aware datetime to Asia/Manila (display form)."""
    return ensure_aware(dt).astimezone(MANILA)
