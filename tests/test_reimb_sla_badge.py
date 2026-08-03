"""R-4-screens — the spec §6.3 derived badge (`on_track`/`due_soon`/`overdue`).

Derived, never stored: a status column that ages is a status column that lies
(workflow-standards §1). Computed server-side so there is one Manila-vs-UTC
boundary in the system rather than one per client.
"""

from __future__ import annotations

from datetime import timedelta

from office_connect.core.time import utc_now
from office_connect.modules.reimbursement.services.actions import (
    DUE_SOON_WINDOW,
    sla_state,
)


def test_no_due_date_means_no_badge():
    """`handed_to_fms` is never stamped (the holder is outside the platform),
    and neither is a draft — both must render no badge at all, not "on track"."""
    assert sla_state(None, now=utc_now()) is None


def test_comfortably_ahead_is_on_track():
    now = utc_now()
    assert sla_state(now + timedelta(days=3), now=now) == "on_track"


def test_inside_the_window_is_due_soon():
    now = utc_now()
    assert sla_state(now + DUE_SOON_WINDOW - timedelta(minutes=1), now=now) == "due_soon"


def test_the_window_boundary_is_inclusive():
    now = utc_now()
    assert sla_state(now + DUE_SOON_WINDOW, now=now) == "due_soon"


def test_past_the_deadline_is_overdue():
    now = utc_now()
    assert sla_state(now - timedelta(seconds=1), now=now) == "overdue"
