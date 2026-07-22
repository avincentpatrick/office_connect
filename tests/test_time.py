"""QA gate: UTC-store / Manila-display convention (Day-1 #2)."""

from datetime import datetime, timedelta, timezone

import pytest

from office_connect.core.time import MANILA, UTC, ensure_aware, to_manila, to_utc, utc_now


def test_utc_now_is_aware_utc():
    now = utc_now()
    assert now.tzinfo is UTC


def test_manila_round_trip():
    stored = datetime(2026, 7, 22, 6, 30, tzinfo=UTC)
    manila = to_manila(stored)
    assert manila.utcoffset() == timedelta(hours=8)  # Asia/Manila, no DST
    assert manila.hour == 14 and manila.minute == 30
    assert to_utc(manila) == stored  # round-trip is lossless


def test_naive_datetime_rejected():
    naive = datetime(2026, 7, 22, 6, 30)
    for fn in (ensure_aware, to_utc, to_manila):
        with pytest.raises(ValueError, match="Naive datetime forbidden"):
            fn(naive)


def test_other_zones_normalize_to_utc():
    tokyo = datetime(2026, 7, 22, 15, 30, tzinfo=timezone(timedelta(hours=9)))
    assert to_utc(tokyo).hour == 6
    assert to_utc(tokyo).tzinfo is UTC
    assert to_manila(tokyo).tzinfo is MANILA
