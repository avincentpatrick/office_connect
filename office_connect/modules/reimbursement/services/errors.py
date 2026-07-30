"""Per-diem engine error codes — thin wrappers over the app's ``APIError``.

Same pattern as ``core/workflow/errors.py``: stable ``code`` slugs a consumer (or
the future wizard/router) branches on. The engine is **fail-closed**: a claim whose
totals cannot be computed correctly raises rather than computing something wrong
(money standards, database-standards.md §10).
"""

from __future__ import annotations

from datetime import date

from office_connect.core.api.errors import APIError


def claim_not_found() -> APIError:
    return APIError(404, "reimb_claim_not_found", "Claim not found.")


def no_computable_days() -> APIError:
    return APIError(
        422,
        "reimb_no_computable_days",
        "The claim has no computable travel days — add itinerary legs "
        "or fix the trip dates.",
    )


def leg_date_required(seq: int) -> APIError:
    return APIError(
        422,
        "reimb_leg_date_required",
        f"Itinerary leg #{seq} has no date — every leg needs one.",
    )


def leg_outside_trip_dates(leg_date: date) -> APIError:
    return APIError(
        422,
        "reimb_leg_outside_trip_dates",
        f"Itinerary leg on {leg_date.isoformat()} falls outside the claim's "
        "departure/return dates.",
    )


def missing_region_cluster(day: date, region_code: str | None) -> APIError:
    where = f"region '{region_code}'" if region_code else "no destination region"
    return APIError(
        422,
        "reimb_missing_region_cluster",
        f"No EO 77 cluster mapping for {where} as of {day.isoformat()} — "
        "set the destination region on the claim or its legs.",
    )


def missing_dte_rate(cluster: str, day: date) -> APIError:
    return APIError(
        422,
        "reimb_missing_dte_rate",
        f"No DTE daily rate for cluster {cluster} as of {day.isoformat()}.",
    )


def config_missing(key: str, day: date) -> APIError:
    return APIError(
        422,
        "reimb_config_missing",
        f"Required config '{key}' has no row effective on {day.isoformat()}.",
    )


def config_invalid(key: str, message: str) -> APIError:
    return APIError(422, "reimb_config_invalid", f"Config '{key}' is invalid: {message}")


def gov_vehicle_fare(seq: int) -> APIError:
    return APIError(
        422,
        "reimb_gov_vehicle_fare",
        f"Itinerary leg #{seq} uses a government vehicle but has a fare — "
        "government-vehicle legs cannot claim fare (EO 77). Remove the fare "
        "or change the transport mode.",
    )


# --- R-4-app lifecycle errors (submit / act / holder resolution) -----------


def claim_already_submitted() -> APIError:
    return APIError(
        409,
        "reimb_claim_already_submitted",
        "This claim is already in the approval workflow.",
    )


def claim_not_reimbursement() -> APIError:
    return APIError(
        422,
        "reimb_claim_not_reimbursement",
        "Only reimbursement-kind claims run on this chain — liquidations "
        "get their own definition (R-6).",
    )


def claimant_no_org_unit() -> APIError:
    return APIError(
        422,
        "reimb_claimant_no_org_unit",
        "The claimant's staff record has no division/section — scoped "
        "approvers cannot be resolved. Fix the directory record first.",
    )


def no_eligible_holder(state_code: str) -> APIError:
    return APIError(
        422,
        "reimb_no_eligible_holder",
        f"No approver holds the '{state_code}' gate's permission for this "
        "claim's org unit — assign the scoped role before routing work here.",
    )


def not_claim_owner() -> APIError:
    return APIError(
        403,
        "reimb_not_claim_owner",
        "Only the claimant may do this (on-behalf filing is not enabled).",
    )


def claim_not_in_workflow() -> APIError:
    return APIError(
        409,
        "reimb_claim_not_in_workflow",
        "This claim has not been submitted — there is no workflow to act on.",
    )


def unsupported_claim_action(action: str) -> APIError:
    return APIError(
        422,
        "reimb_unsupported_claim_action",
        f"'{action}' is not a claim action (submit via submit_claim; "
        "approve/return/resubmit/cancel via claim_action).",
    )
