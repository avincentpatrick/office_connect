"""Typed transition guards — pure, no I/O, no DSL (design doc PITFALL).

A guard is a precondition on a transition; only a transition whose guard passes may
fire. Guards are **typed columns** (amount band), never a free-form expression
language — that keeps routing auditable and indexable. The actor's permission is an
*authorization* check handled in ``transitions``/``delegation``, not a routing guard.
"""

from __future__ import annotations

from decimal import Decimal

from office_connect.core.models import WorkflowInstance, WorkflowTransition


def amount_guard_passes(transition: WorkflowTransition, instance: WorkflowInstance) -> bool:
    """True if the instance's ``amount`` falls in the transition's [min, max] band.

    A NULL bound is open on that side. If a bound is set but the instance has no
    amount, the guard fails (an amount-gated route needs an amount to route on)."""
    amount: Decimal | None = instance.amount
    if transition.min_amount is not None:
        if amount is None or amount < transition.min_amount:
            return False
    if transition.max_amount is not None:
        if amount is None or amount > transition.max_amount:
            return False
    return True
