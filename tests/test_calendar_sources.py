"""Stage D-2 — the CALENDAR SOURCE CENSUS, and the registry's own invariants.

**Why this file exists, stated plainly, because it is the whole point.**

The calendar's travel source is the FOURTH consumer of
``services/queue.py::oversight_scope``. The two tests that exist to catch
"surface number five got api-standards §9f wrong" cannot see it:

- ``tests/test_reimb_authz_census.py`` filters routes on the
  ``/api/v1/reimbursement`` prefix. ``/api/v1/calendar`` is a CORE route, so
  ``_observed()`` never returns it and ``AUTHZ_TABLE`` never grows a row.
- ``tests/test_reimb_scope_security.py``'s ``census drift`` assertion is derived
  from that same table, so it stays at 3 too.

Both stay green whatever the calendar does. That is a gap, not a pass — and it
is exactly the shape R-9 warned about: *absence never fails a test*. This file
is the third instance of that census pattern, after ``AUTHZ_TABLE`` (routes) and
``NAV_CENSUS`` (nav rows).

A source added without a row here fails with its key in the message.
"""

from __future__ import annotations

import pytest

from office_connect.core.calendar import (
    CalendarSource,
    register_source,
    registered_sources,
)

#: ``key -> (label, feature_flag, a fragment the scope_rule must contain)``.
#:
#: The fragment is checked with ``in`` rather than ``==`` on purpose: the full
#: rule strings are paragraphs, and pinning them verbatim would make this file
#: fail on a comment rewording — a census that cries wolf gets deleted. What must
#: not drift silently is WHICH RULE each source claims to apply.
SOURCE_CENSUS: dict[str, tuple[str, str | None, str]] = {
    "core.activity": (
        "Activities",
        None,
        "TENANT-WIDE",
    ),
    "reimb.travel": (
        "Travel",
        "module.reimbursement",
        "oversight_scope",
    ),
    "reimb.liquidation": (
        "Liquidation deadlines",
        "module.reimbursement",
        "OWN advances only",
    ),
}


def _observed() -> dict[str, CalendarSource]:
    """Sources as the RUNNING APP has them.

    Imports ``office_connect.main`` for the same reason
    ``test_reimb_authz_census.py::_observed`` does: registration happens at the
    composition root, so a census that imported ``core.calendar`` alone would
    see only core's own source and would pass while every module contribution
    was missing.
    """
    import office_connect.main  # noqa: F401  (the import IS the registration)

    return {source.key: source for source in registered_sources()}


def test_every_registered_source_has_a_census_row():
    """A new source without a row here fails, with its key in the message."""
    undeclared = set(_observed()) - set(SOURCE_CENSUS)
    assert not undeclared, (
        f"calendar sources with no census row: {sorted(undeclared)}. "
        "Add them to SOURCE_CENSUS above, naming the exact scope rule each "
        "applies — a source nobody wrote down is a source nobody reviewed."
    )


def test_the_census_carries_no_stale_rows():
    """The other direction: a removed source must not leave a row behind."""
    missing = set(SOURCE_CENSUS) - set(_observed())
    assert not missing, f"census rows for sources that no longer register: {sorted(missing)}"


@pytest.mark.parametrize("key", sorted(SOURCE_CENSUS))
def test_each_source_declares_the_gate_and_rule_the_census_records(key):
    observed = _observed()[key]
    label, flag, rule_fragment = SOURCE_CENSUS[key]
    assert observed.label == label
    assert observed.feature_flag == flag, (
        f"{key}: feature flag drifted. A module source that loses its flag "
        "becomes visible while the module is switched off (api-standards §9k)."
    )
    assert rule_fragment in observed.scope_rule, (
        f"{key}: scope_rule no longer mentions {rule_fragment!r}.\n"
        f"got: {observed.scope_rule}"
    )


def test_every_source_declares_a_non_empty_scope_rule():
    """The property behind the table — true of sources this file has not met."""
    for source in _observed().values():
        assert source.scope_rule.strip(), (
            f"{source.key} declares no scope rule. This is refused at "
            "registration; seeing it here means the guard was removed."
        )


def test_a_source_with_no_scope_rule_cannot_register():
    """The guard itself. Load-bearing: it makes the omission impossible at
    IMPORT time, before any test runs — which is the difference between a rule
    and a reminder."""
    with pytest.raises(ValueError, match="scope_rule"):
        register_source(
            CalendarSource(key="test.no_rule", label="No rule", fetch=None)
        )
    assert "test.no_rule" not in _observed()


def test_registration_is_idempotent_by_construction():
    """``tests/`` import ``office_connect.main`` from many modules. A registry
    backed by a list would DOUBLE every event the second time it was imported,
    and the symptom would be a calendar that shows each trip twice — on a demo
    box, intermittently, depending on import order."""
    before = _observed()
    original = before["core.activity"]

    register_source(original)
    register_source(original)

    after = _observed()
    assert len(after) == len(before)
    assert after["core.activity"] is original


def test_sources_are_key_sorted_regardless_of_registration_order():
    """Same reasoning as D-1's ``sorted()`` on ``/auth/me``: an order that
    depends on import order is non-deterministic as a function of HOW the app
    was loaded — stable on a dev box, arbitrary elsewhere."""
    keys = [source.key for source in registered_sources()]
    assert keys == sorted(keys)


def test_the_travel_source_names_the_server_rule_it_shares_with_the_queue():
    """The cross-reference that closes the census gap in the other direction.

    ``oversight_scope`` lives in the reimbursement module and is graded by
    ``test_reimb_scope_security.py``. This assertion is what makes a reader of
    THAT file discoverable from here, and it names the symbol so a rename
    surfaces as a failure rather than as a stale sentence.
    """
    rule = _observed()["reimb.travel"].scope_rule
    assert "queue.py" in rule and "oversight_scope" in rule
    assert "base_query" in rule


def test_the_liquidation_source_does_not_claim_a_scope_rule_that_does_not_exist():
    """It reads OWN advances. ``can_read_cash_advance`` is a per-ROW rule with no
    set form anywhere in the codebase, and a source claiming to apply it would be
    claiming a guarantee nothing implements (calendar.md §6b)."""
    rule = _observed()["reimb.liquidation"].scope_rule
    assert "OWN advances only" in rule
    assert "NOT deps.can_read_cash_advance" in rule
