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


def return_reason_required() -> APIError:
    """R-4-screens: spec §5.6/§9.4 — a return carries ≥1 taxonomy reason. The
    engine's ``requires_comment`` covers the prose; this covers the STRUCTURE
    the R-8 learning loop reads."""
    return APIError(
        422,
        "reimb_return_reason_required",
        "Select at least one reason for returning this claim.",
    )


def unknown_return_reason(reason_ids: list[int]) -> APIError:
    listed = ", ".join(str(i) for i in reason_ids)
    return APIError(
        422,
        "reimb_unknown_return_reason",
        f"Return reason id(s) {listed} are not in the active return-reason "
        "taxonomy — pick from the published catalog.",
    )


def unsupported_claim_action(action: str) -> APIError:
    return APIError(
        422,
        "reimb_unsupported_claim_action",
        f"'{action}' is not a claim action (submit via submit_claim; "
        "approve/return/resubmit/cancel via claim_action).",
    )


# --- R-3 checklist / documentary-requirements errors ------------------------


def packet_incomplete(items, *, actor_is_owner: bool = True) -> APIError:
    """Spec §2: "a claim physically cannot be submitted with a missing required
    item". The message NAMES the blockers and says what to do next — spec §9.1
    principle 4 ("never block without a path") makes a bare refusal a defect —
    and ``details`` carries the full machine-readable list the Documents step
    deep-links from."""
    listed = ", ".join(f"{i.code} ({i.label})" for i in items[:5])
    more = f", and {len(items) - 5} more" if len(items) > 5 else ""
    remedy = (
        "Attach them on the Documents step, then submit again."
        if actor_is_owner
        else "Return the claim so the claimant can complete the packet."
    )
    noun = "document" if len(items) == 1 else "documents"
    return APIError(
        422,
        "reimb_packet_incomplete",
        f"{len(items)} required {noun} still missing: {listed}{more}. {remedy}",
        details=[
            {
                "catalog_id": i.catalog_id,
                "item_id": i.item_id,
                "code": i.code,
                "label": i.label,
                "group": i.group,
                "evidence": i.evidence,
                "reason": i.reason,
            }
            for i in items
        ],
    )


def unknown_catalog_item(catalog_id: int) -> APIError:
    return APIError(
        422,
        "reimb_unknown_catalog_item",
        f"Checklist item {catalog_id} is not in the active catalog for this "
        "claim — refresh the packet and try again.",
    )


def evidence_not_uploadable(code: str, evidence: str) -> APIError:
    return APIError(
        422,
        "reimb_evidence_not_uploadable",
        f"'{code}' is a {evidence.replace('_', ' ')} item — there is nothing "
        "for you to upload against it.",
    )


def evidence_not_on_item(attachment_id: int) -> APIError:
    return APIError(
        422,
        "reimb_evidence_not_on_item",
        f"Attachment {attachment_id} is not filed against that checklist item.",
    )


# --- R-5 document generation ------------------------------------------------


def totals_missing() -> APIError:
    """No money snapshot — refuse to print rather than print zeros.

    ``drafts.py`` clears ``claim.totals`` whenever a compute input changes, so an
    empty snapshot means the numbers are mid-edit. An official-looking voucher
    for ₱0.00 is far worse than a claim that says "work out the money first".
    """
    return APIError(
        422,
        "reimb_totals_missing",
        "The claim's amounts have not been worked out yet — complete the "
        "Money step, then the packet can be generated.",
    )


def unknown_catalog_code(code: str) -> APIError:
    return APIError(
        422,
        "reimb_unknown_catalog_code",
        f"'{code}' is not in the active catalog for this claim kind — the "
        "template binding points at a requirement that no longer exists.",
    )


def document_not_generatable(code: str, evidence: str) -> APIError:
    return APIError(
        422,
        "reimb_document_not_generatable",
        f"'{code}' is a {evidence.replace('_', ' ')} item — the system does "
        "not generate it.",
    )


# --- R-2-wizard draft/API errors --------------------------------------------


def no_staff_link() -> APIError:
    return APIError(
        422,
        "reimb_no_staff_link",
        "Your login is not linked to a staff record — claims are filed "
        "against the directory. Ask an administrator to link your account.",
    )


def claim_not_editable() -> APIError:
    return APIError(
        409,
        "reimb_claim_not_editable",
        "This claim is in the approval workflow and can no longer be edited — "
        "wait for it to be returned, or cancel and start again.",
    )


def leg_unknown(leg_id: int) -> APIError:
    return APIError(
        422,
        "reimb_leg_unknown",
        f"Itinerary leg id {leg_id} does not belong to this claim.",
    )


def unknown_activity(activity_id: int) -> APIError:
    return APIError(
        422,
        "reimb_unknown_activity",
        f"Activity {activity_id} does not exist — pick one from the "
        "activity spine or leave the claim unlinked.",
    )


def invalid_trip_dates() -> APIError:
    return APIError(
        422,
        "reimb_invalid_trip_dates",
        "The return date is before the departure date — fix the trip dates.",
    )


def claim_cancelled() -> APIError:
    return APIError(
        409,
        "reimb_claim_cancelled",
        "This claim was cancelled — cancelled claims cannot be revived. "
        "Start a new claim instead.",
    )


# --- R-6-clock cash advances + the 30-day liquidation clock -----------------


def cash_advance_not_found() -> APIError:
    return APIError(404, "reimb_cash_advance_not_found", "Cash advance not found.")


def cash_advance_unliquidated(*, dv_no: str | None, deadline: date | None) -> APIError:
    """PD 1445 §89 — one unliquidated travel advance per person, at a time.

    The rule is a partial-unique DB index (R-1 decision: a data-integrity rule,
    not a workflow guard), so without this the violation surfaces as a raw
    ``IntegrityError`` → 500. A 500 tells the Admin Officer nothing; this names
    the blocking advance and what clears it, per §9.1 principle 4.
    """
    which = f"DV {dv_no}" if dv_no else "an earlier advance"
    due = f" (due {deadline.isoformat()})" if deadline else ""
    return APIError(
        409,
        "reimb_cash_advance_unliquidated",
        f"This claimant still has an unliquidated cash advance — {which}{due}. "
        "PD 1445 §89 allows only one at a time: liquidate or settle that one "
        "before recording another.",
    )


def cash_advance_settled() -> APIError:
    return APIError(
        409,
        "reimb_cash_advance_settled",
        "This cash advance is already settled — settled advances are a closed "
        "record and cannot be edited.",
    )


def cash_advance_amount_invalid() -> APIError:
    return APIError(
        422,
        "reimb_cash_advance_amount_invalid",
        "A cash advance must be for more than ₱0.00.",
    )


def cash_advance_dates_invalid() -> APIError:
    return APIError(
        422,
        "reimb_cash_advance_dates_invalid",
        "The return date is before the DV date — a travel advance cannot be "
        "liquidated before it was issued. Check the dates.",
    )


# --- R-6-liq-chain: the liquidation workflow -------------------------------


def liquidation_exists(*, claim_id: int | None, ref_no: str | None) -> APIError:
    """One live liquidation per advance.

    Names the existing one so the caller can open it — a bare "already exists"
    would leave a traveller with a button that fails and no way to find the
    liquidation they already started (§9.1 principle 4).

    Degrades to an unnamed sentence when raised from the ``IntegrityError``
    behind the pre-flight (migration ``0020``'s belt): that path lost a race and
    its session is aborted, so it cannot query for the winner.
    """
    if claim_id is None:
        return APIError(
            409,
            "reimb_liquidation_exists",
            "This cash advance already has a liquidation. Reload to open it.",
        )
    which = f"{ref_no} " if ref_no else ""
    return APIError(
        409,
        "reimb_liquidation_exists",
        f"This cash advance already has a liquidation ({which}#{claim_id}). "
        "Open that one instead of starting another.",
        details=[{"claim_id": claim_id, "ref_no": ref_no}],
    )


def cash_advance_already_settled_for_liquidation() -> APIError:
    return APIError(
        409,
        "reimb_cash_advance_settled",
        "This cash advance is already settled — there is nothing left to "
        "liquidate.",
    )


def not_advance_holder() -> APIError:
    """Only the traveller who holds the advance may liquidate it.

    Deliberately the same shape as ``not_claim_owner``: liquidating is
    certification A, and A certifies that the CLAIMANT incurred the expenses.
    An Admin Officer filing on their behalf would put the wrong person's name
    against a COA certification (the same reasoning that keeps submit
    owner-only — delta row 43).
    """
    return APIError(
        403,
        "reimb_not_advance_holder",
        "Only the traveller this cash advance was issued to can liquidate it.",
    )


# --- R-6-liq-settle: recording the settlement ------------------------------


def settlement_required(*, claim_id: int) -> APIError:
    """``settled`` asserts the advance is closed — refuse to assert it early.

    The engine's ``approve`` carries no payload, so the money is recorded by a
    separate, prior service call inside the same transaction. This is what makes
    the generic approve route refuse to be the one that closes a liquidation,
    and it NAMES the route that does the thing (§9.1 principle 4) rather than
    leaving an Admin Officer holding a button that always fails.
    """
    return APIError(
        409,
        "reimb_settlement_required",
        "Record the settlement before closing this liquidation — the refund "
        "receipt or the amount still due has to be on the cash advance first.",
        details=[{"claim_id": claim_id, "action": "settle"}],
    )


def liquidation_without_advance() -> APIError:
    return APIError(
        409,
        "reimb_liquidation_without_advance",
        "This liquidation is not linked to a cash advance, so there is nothing "
        "to settle.",
    )


def not_a_liquidation() -> APIError:
    return APIError(
        422,
        "reimb_not_a_liquidation",
        "Only a liquidation is settled against a cash advance — a reimbursement "
        "claim is paid, not settled.",
    )


def settlement_wrong_state(*, status: str) -> APIError:
    return APIError(
        409,
        "reimb_settlement_wrong_state",
        f"A liquidation is settled once FMS has processed it; this one is "
        f"'{status}'. Walk the certifications first.",
    )


def settlement_already_recorded(*, or_no: str | None, settled_at: date | None) -> APIError:
    """The double-tap answer.

    Deliberately NOT the engine's generic ``workflow_state_conflict`` ("someone
    finished it first"), which is a sentence about a race — this is a sentence
    about a repeat, and the difference matters to whoever is reading it.
    """
    when = f" on {settled_at.isoformat()}" if settled_at else ""
    which = f" (OR {or_no})" if or_no else ""
    return APIError(
        409,
        "reimb_settlement_already_recorded",
        f"This cash advance was already settled{when}{which}. A settled advance "
        "is a closed record.",
    )


def settlement_totals_missing() -> APIError:
    return APIError(
        422,
        "reimb_settlement_totals_missing",
        "This liquidation's amounts have not been worked out, so there is no "
        "settlement figure to record. Recompute the claim first.",
    )


def refund_receipt_required(*, amount: str) -> APIError:
    return APIError(
        422,
        "reimb_refund_receipt_required",
        f"₱{amount} is refundable, so the DOH official receipt number and date "
        "are required — the receipt is the only proof the money came back.",
    )


def refund_receipt_not_applicable() -> APIError:
    """An OR where nothing was refunded is a receipt for a payment that never
    happened — and it is the line a COA auditor traces from the Liquidation
    Report into the books."""
    return APIError(
        422,
        "reimb_refund_receipt_not_applicable",
        "Nothing is refundable on this liquidation, so there is no official "
        "receipt to record.",
    )


def refund_amount_mismatch(*, expected: str, given: str) -> APIError:
    """Money is server-computed (standing prohibition). A client may ECHO the
    figure back so a stale screen is caught; it may never propose one."""
    return APIError(
        422,
        "reimb_refund_amount_mismatch",
        f"The refund on this liquidation is ₱{expected}, not ₱{given} — your "
        "screen is out of date. Reload and record it again.",
    )


def spawn_not_over_advance(*, mode: str | None) -> APIError:
    which = f"settled as '{mode}'" if mode else "has not been settled yet"
    return APIError(
        409,
        "reimb_spawn_not_over_advance",
        "A reimbursement is only claimed when the actual expenses exceeded the "
        f"advance; this liquidation {which}.",
    )


def spawn_exists(*, claim_id: int | None, ref_no: str | None) -> APIError:
    """Names the existing one, the same shape as ``liquidation_exists``.

    Degrades to an unnamed sentence when raised from the ``IntegrityError``
    behind the pre-flight: that path lost a race and its session is aborted, so
    it cannot query for the winner. Naming the wrong claim would be worse than
    naming none — the ``create_cash_advance`` precedent, same reasoning.
    """
    if claim_id is None:
        return APIError(
            409,
            "reimb_spawn_exists",
            "This liquidation already has its reimbursement claim. Reload to "
            "open it.",
        )
    which = f"{ref_no} " if ref_no else ""
    return APIError(
        409,
        "reimb_spawn_exists",
        f"This liquidation already has its reimbursement claim ({which}"
        f"#{claim_id}). Open that one instead of starting another.",
        details=[{"claim_id": claim_id, "ref_no": ref_no}],
    )


def spawn_below_advance() -> APIError:
    """A reimbursement claim can never print "Amount refundable" — that is a
    liquidation's sentence, on a liquidation's form."""
    return APIError(
        422,
        "reimb_spawn_below_advance",
        "This claim now totals less than the cash advance it nets, so nothing "
        "is due to you. Check the itinerary and the other expenses.",
    )


def queue_not_permitted() -> APIError:
    """R-7-queue. Distinct from ``not_claim_owner`` on purpose.

    That slug says "only the claimant may do this", which is exactly wrong here:
    the refusal is that the actor oversees NOBODY, not that they failed to own
    some particular claim. There is also no row to leak about — the request
    names none — so the honest message costs nothing, and it names the surface
    that does answer the question the actor was actually asking (§9.1
    principle 4).
    """
    return APIError(
        403,
        "reimb_queue_not_permitted",
        "This queue shows other people's claims, so it is for approvers and "
        "the Admin Officer. Your own claims are on My Work.",
    )
