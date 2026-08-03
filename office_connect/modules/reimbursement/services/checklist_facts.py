"""The claim facts the checklist grammar evaluates against — a PUBLISHED contract.

``core/checklist`` is pure and knows nothing about claims; this module is the
adapter that turns a ``ReimbClaim`` (plus its legs and the effective config pack)
into the plain mapping the rule grammar reads. Every key here is referenced BY
NAME from seeded JSONB (``{"field": "totals.other"}``), so this is an interface,
not an implementation detail — it is versioned like ``reimb_claims.totals`` and
renaming a key is a catalog migration, not a refactor.

Money is emitted as 2-dp STRINGS throughout (``core/money.money_str``), matching
the ``totals`` snapshot; the grammar's ``gt`` comparator coerces them back to
``Decimal``.

Read-only: builds nothing, writes nothing, commits nothing.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.money import money_str
from office_connect.core.time import to_manila, utc_now
from office_connect.modules.reimbursement.models import (
    ReimbClaim,
    ReimbConfig,
    ReimbItineraryLeg,
)

#: Bump when a key changes meaning or disappears — the catalog references these
#: by name, so a rename is a data migration.
FACTS_VERSION = 1


async def effective_config(session: AsyncSession, *, today) -> dict[str, Any]:
    """Every ``reimb_configs`` key at its latest row effective on ``today``.

    Keys are kept VERBATIM (``"receipts.cenrr_max"``, dots and all) and values
    exactly as stored — ``core.checklist.checks`` owns the ``{"amount": …}``
    unwrapping, so the convention is one thing DTWIS inherits rather than
    something each consumer re-invents. A tenant row wins over the platform
    default for the same key and date.
    """
    rows = (
        (
            await session.execute(
                select(ReimbConfig).where(
                    ReimbConfig.is_active.is_(True),
                    ReimbConfig.effective_from <= today,
                )
            )
        )
        .scalars()
        .all()
    )
    best: dict[str, ReimbConfig] = {}
    for row in rows:
        current = best.get(row.key)
        if current is None:
            best[row.key] = row
            continue
        # Later effective date wins; on a tie a tenant override beats the default.
        newer = (row.effective_from, row.tenant_id is not None) > (
            current.effective_from,
            current.tenant_id is not None,
        )
        if newer:
            best[row.key] = row
    return {key: row.value for key, row in best.items()}


async def build_claim_facts(
    session: AsyncSession,
    *,
    claim: ReimbClaim,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Assemble the fact mapping for one claim."""
    now = now or utc_now()
    today = to_manila(now).date()

    legs = (
        (
            await session.execute(
                select(ReimbItineraryLeg)
                .where(ReimbItineraryLeg.claim_id == claim.id)
                .order_by(ReimbItineraryLeg.seq, ReimbItineraryLeg.id)
            )
        )
        .scalars()
        .all()
    )

    leg_facts = [
        {
            "seq": leg.seq,
            "leg_date": leg.leg_date.isoformat() if leg.leg_date else None,
            "place": leg.place,
            "destination_region_code": leg.destination_region_code,
            "transport_mode": leg.transport_mode,
            "fare": money_str(leg.fare) if leg.fare is not None else None,
        }
        for leg in legs
    ]
    # Sorted-unique so a rule's outcome does not depend on row order. The global
    # soft-delete filter already excludes removed legs, which is what makes
    # "deleted the taxi leg → RER-46 stops applying" work.
    transport_modes = sorted({leg.transport_mode for leg in legs if leg.transport_mode})

    trip_days = None
    if claim.date_depart and claim.date_return:
        trip_days = (claim.date_return - claim.date_depart).days + 1

    return {
        "kind": claim.kind,
        "is_jo_cos": bool(claim.is_jo_cos),
        "fund_source": claim.fund_source,
        "is_within_50km": bool(claim.is_within_50km),
        "overnight_stay": bool(claim.overnight_stay),
        "activity_id": claim.activity_id,
        "purpose": claim.purpose,
        "destination": claim.destination,
        "destination_region_code": claim.destination_region_code,
        "transport_modes": transport_modes,
        # Per-leg, because there is no claim-level fare; `amount_threshold`
        # handles a list by flagging if ANY element exceeds the ceiling.
        "fare": [leg["fare"] for leg in leg_facts if leg["fare"] is not None],
        "legs": leg_facts,
        "leg_count": len(legs),
        "trip": {
            "depart": claim.date_depart.isoformat() if claim.date_depart else None,
            "return": claim.date_return.isoformat() if claim.date_return else None,
            "days": trip_days,
        },
        # `other` is overlaid from the COLUMN, not read out of the snapshot:
        # `drafts.py` clears `claim.totals` whenever a compute input changes, so
        # a snapshot read would make LOD-01 silently stop being required in the
        # middle of an edit. Since migration 0016 the column is the truth.
        "totals": {
            **(claim.totals or {}),
            "other": money_str(claim.other_total or 0),
        },
        "config": await effective_config(session, today=today),
        # Substrate that does not exist yet. Present and empty so the checks that
        # read them report "not checked" rather than silently passing.
        "deadlines": {},  # R-6 (the liquidation clock)
        "evidence_dates": [],  # R-9 (OCR)
        "ocr_text": None,  # R-9 (OCR)
        "today": today.isoformat(),
        "facts_version": FACTS_VERSION,
    }
