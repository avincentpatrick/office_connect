"""Reimbursement reference-data seeds — public config/law, loads in every environment.

Lives in the MODULE (not core/seeds/datasets.py) because core may not import module
models (lint-imports). Consumes the core seed framework (`apply_dataset`, idempotent
upsert by natural key). Covers the §4 config pack (with legal sources for display), the
EO 77 3-cluster DTE rates + PSGC region→cluster map (the delta that supersedes the
spec's 2-tier per diem), a representative COA 2023-004 checklist catalog, and the
return-reason taxonomy. Run via `apply_reimbursement_seeds(session)`.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from office_connect.core.seeds import SeedDataset, apply_dataset
from office_connect.modules.reimbursement.models import (
    ReimbChecklistCatalog,
    ReimbConfig,
    ReimbDteCluster,
    ReimbRegionCluster,
    ReimbReturnReasonCatalog,
    ReimbTemplateMap,
)

_ALL = ("all",)
_EO77 = date(2019, 3, 15)  # EO 77 s.2019 effective anchor
_CFG = date(2020, 1, 1)  # config-regime anchor
_COA_CHECKLIST = "COA Circular 2023-004"


def _cfg(key: str, value: dict[str, Any], display: str, source: str) -> dict[str, Any]:
    return {
        "key": key,
        "value": value,
        "value_display": display,
        "source": source,
        "effective_from": _CFG,
        "tenant_id": None,
    }


# --- §4 config pack (non-rate; per-diem RATES live in reimb_dte_clusters) ---
REIMB_CONFIGS = SeedDataset(
    name="reimb_configs",
    owner="Accounting Unit / Admin",
    cadence="on_revision",
    environments=_ALL,
    model=ReimbConfig,
    natural_key=("key", "effective_from", "tenant_id"),
    rows=(
        _cfg("per_diem.apportionment",
             {"lodging": 50, "meals": 30, "incidentals": 20},
             "50% lodging / 30% meals / 20% incidentals", "EO 77 s.2019"),
        _cfg("per_diem.departure_day_rate", {"pct": 50},
             "50% of daily rate on the departure/return day", "EO 77 s.2019"),
        _cfg("per_diem.radius_km", {"km": 50},
             "Full DTE only beyond 50 km from the official station", "EO 77 s.2019"),
        # R-0 item 1, CLOSED 2026-08-04: calendar days per COA's text, with the
        # basis honoured as data (services/deadline.py reads it) so confirming
        # DOH working-day practice later is a config edit, not a code change.
        _cfg("liquidation.deadline", {"days": 30, "basis": "calendar"},
             "30 calendar days after return to official station",
             "COA Circular 97-002"),
        _cfg("liquidation.accountant_verify_days", {"days": 10},
             "Accountant verifies within 10 days (informational)",
             "COA Circular 97-002"),
        # The D-0 warning copy. Config rather than a Python string because it
        # states a legal consequence and must be displayed WITH its source
        # (spec §4: "displayed with their legal source") — and because the
        # resident COA auditor, not a developer, owns that wording.
        _cfg("liquidation.overdue_note",
             {"text": "Unliquidated advances may accrue 6% interest and be "
                      "deducted from your salary."},
             "COA warning shown at and past the liquidation deadline",
             "COA Circular 97-002"),
        _cfg("receipts.cenrr_max", {"amount": "300.00"},
             "No-receipt fares up to ₱300 → CENRR", "COA Circular 2021-001"),
        _cfg("receipts.rer_range", {"min": "300.00", "max": "1000.00"},
             ">₱300–₱1,000 → RER", "COA Circular 2021-001"),
        _cfg("fare.class", {"class": "economy"},
             "Economy only; above-rate needs Head-of-Agency certification",
             "EO 77 s.2019"),
        _cfg("jo_cos.extra_requirements", {"enabled": True},
             "JO/COS claimants require Head-of-Office certification + approval",
             "DM 2025-0202 / -0202A"),
        _cfg("sla.approval_working_days", {"working_days": 3},
             "Each approval step is due in 3 working days",
             "build spec §7 (work-management)"),
        _cfg("sla.reminder_repeat_days", {"working_days": 2},
             "Reminder repeats every 2 working days (holder only)",
             "build spec §7 (work-management)"),
        # R-7-queue. NOT an SLA in the §7.4 sense — the holder is FMS, outside
        # the platform, so nothing is stamped on the step and nobody is nudged
        # (lifecycle._stamp_sla skips external states deliberately). This is the
        # threshold for the Admin Officer's own follow-up FILTER, which is what
        # §7 rule 5 actually asks for.
        _cfg("sla.external_followup_working_days", {"working_days": 10},
             "Flag a claim for FMS follow-up after 10 working days",
             "build spec §7 rule 5 (work-management)"),
    ),
)

# --- EO 77 Annex A — 3 DTE clusters by DESTINATION region ------------------
REIMB_DTE_CLUSTERS = SeedDataset(
    name="reimb_dte_clusters",
    owner="Accounting Unit / Admin",
    cadence="on_revision",
    environments=_ALL,
    model=ReimbDteCluster,
    natural_key=("cluster", "effective_from"),
    rows=(
        {"cluster": "I", "daily_rate": Decimal("1500.00"), "label": "Cluster I",
         "source": "EO 77 s.2019 Annex A", "effective_from": _EO77},
        {"cluster": "II", "daily_rate": Decimal("1800.00"), "label": "Cluster II",
         "source": "EO 77 s.2019 Annex A", "effective_from": _EO77},
        {"cluster": "III", "daily_rate": Decimal("2200.00"), "label": "Cluster III",
         "source": "EO 77 s.2019 Annex A", "effective_from": _EO77},
    ),
)


def _region(code: str, name: str, cluster: str) -> dict[str, Any]:
    return {
        "region_code": code, "region_name": name, "cluster": cluster,
        "effective_from": _EO77,
    }


# PSGC region code → EO 77 cluster (all 17 regions).
REIMB_REGION_CLUSTERS = SeedDataset(
    name="reimb_region_clusters",
    owner="Accounting Unit / Admin",
    cadence="on_revision",
    environments=_ALL,
    model=ReimbRegionCluster,
    natural_key=("region_code", "effective_from"),
    rows=(
        _region("13", "NCR", "III"),
        _region("04", "Region IV-A (CALABARZON)", "III"),
        _region("17", "Region IV-B (MIMAROPA)", "III"),
        _region("14", "CAR", "II"),
        _region("06", "Region VI (Western Visayas)", "II"),
        _region("07", "Region VII (Central Visayas)", "II"),
        _region("10", "Region X (Northern Mindanao)", "II"),
        _region("11", "Region XI (Davao)", "II"),
        _region("01", "Region I (Ilocos)", "I"),
        _region("02", "Region II (Cagayan Valley)", "I"),
        _region("03", "Region III (Central Luzon)", "I"),
        _region("05", "Region V (Bicol)", "I"),
        _region("08", "Region VIII (Eastern Visayas)", "I"),
        _region("09", "Region IX (Zamboanga Peninsula)", "I"),
        _region("12", "Region XII (SOCCSKSARGEN)", "I"),
        _region("16", "Region XIII (Caraga)", "I"),
        _region("19", "BARMM", "I"),
    ),
)


def _check(code, label, group, evidence, required_rule, *, auto_checks=(), sort=0,
           claim_kind="reimbursement") -> dict[str, Any]:
    return {
        "claim_kind": claim_kind,
        "code": code,
        "label": label,
        "group": group,
        "evidence": evidence,
        "required_rule": required_rule,
        "auto_checks": list(auto_checks),
        "circular_version": _COA_CHECKLIST,
        "sort": sort,
    }


# --- Documentary-requirements catalog (representative COA 2023-004 subset) --
# The rule GRAMMAR that interprets required_rule/auto_checks is built at R-3.
REIMB_CHECKLIST = SeedDataset(
    name="reimb_checklist_catalogs",
    owner="Accounting Unit / resident COA auditor",
    cadence="on_revision",
    environments=_ALL,
    model=ReimbChecklistCatalog,
    natural_key=("claim_kind", "code"),
    rows=(
        _check("TO-01", "Approved Travel Order / Authority to Travel",
               "authority", "upload", {"always": True}, sort=1),
        _check("JO-01", "Head-of-Office certification (JO/COS claimant)",
               "authority", "upload",
               {"if": {"field": "is_jo_cos", "eq": True}}, sort=2),
        _check("IOT-45", "Itinerary of Travel (GAM App 45)",
               "itinerary", "generated_doc", {"always": True}, sort=3),
        _check("CTC-47", "Certificate of Travel Completed (GAM App 47)",
               "proof_of_travel", "external_wet_sign", {"always": True}, sort=4),
        _check("RER-46", "Reimbursement Expense Receipt for taxi/no-receipt fares",
               "transport", "upload",
               {"if": {"field": "transport_modes", "contains": "taxi"}},
               auto_checks=(
                   {"type": "amount_threshold", "field": "fare",
                    "max_key": "receipts.cenrr_max", "on_exceed": "require_item:RER"},
               ), sort=5),
        _check("LOD-01", "Hotel official receipt / lodging certificate",
               "lodging_meals", "upload",
               {"if": {"field": "totals.other", "gt": 0}}, sort=6),
        _check("AR-01", "Accomplishment / after-travel report",
               "report", "generated_doc", {"always": True}, sort=7),
        _check("DV-32", "Disbursement Voucher (GAM App 32)",
               "financial", "generated_doc", {"always": True}, sort=8),

        # --- Liquidation set (R-6-liq-chain) -------------------------------
        # The natural key is (claim_kind, code), so TO-01 and CTC-47 appear
        # under BOTH kinds deliberately: a traveller who took an advance files
        # a LIQUIDATION, one who did not files a REIMBURSEMENT, and the trip and
        # its documentary proof are identical either way. No claimant is asked
        # twice — a claim is exactly one kind.
        _check("TO-01", "Approved Travel Order / Authority to Travel",
               "authority", "upload", {"always": True}, sort=1,
               claim_kind="liquidation"),
        _check("CTC-47", "Certificate of Travel Completed (GAM App 47)",
               "proof_of_travel", "external_wet_sign", {"always": True}, sort=2,
               claim_kind="liquidation"),
        _check("OR-01", "Official receipts / RERs for the actual expenses",
               "financial", "upload", {"always": True}, sort=3,
               claim_kind="liquidation"),
        # THE FIRST SEEDED `deadline_check` — its substrate shipped at R-6-clock
        # (facts["deadlines"] keyed by CONFIG KEY, FACTS_VERSION 2), and this is
        # the rule that discharges it. `data_only` on purpose: the claim's own
        # dates ARE the evidence, there is nothing to attach, and a data_only
        # item never blocks (delta row 67) while still being able to flag. That
        # is exactly right for a passed deadline — the approver must SEE it and
        # decide, but a late traveller must never be trapped unable to file the
        # very liquidation that ends the lateness.
        _check("LIQ-30", "Filed within the 30-day liquidation deadline",
               "financial", "data_only", {"always": True},
               auto_checks=(
                   {"type": "deadline_check", "key": "liquidation.deadline"},
               ), sort=4, claim_kind="liquidation"),
        # Inert until R-6-liq-settle binds it to GAM App 44: a generated_doc
        # item never blocks, so an unbound row is visibly "not produced yet"
        # rather than a silent pass — the same honest-inertness doctrine that
        # kept `deadline_check` registered-but-skipped for three sessions.
        _check("LR-44", "Liquidation Report (GAM App 44)",
               "financial", "generated_doc", {"always": True}, sort=5,
               claim_kind="liquidation"),
        # Certification C's wet-signed page. Deliberately NOT required: the
        # checklist gate is a PRE-workflow gate (it runs at submit and at every
        # approve), so a required row here would block submit and certification
        # B as well — demanding the Accounting head's signature before the
        # chain that obtains it has even started. That is delta row 67's
        # argument ("a system-produced artifact cannot be a precondition of the
        # workflow that produces it") one level out. The row exists so the
        # signed page has a home; the RECORD of certification C is the Admin
        # Officer clearing the gate under its mandatory comment.
        _check("CRT-C", "Certification C — signed page (Head, Accounting Unit)",
               "financial", "external_wet_sign", {"always": False}, sort=6,
               claim_kind="liquidation"),
    ),
)

# --- Return-reason taxonomy ------------------------------------------------
REIMB_RETURN_REASONS = SeedDataset(
    name="reimb_return_reason_catalogs",
    owner="Admin Officer / resident COA auditor",
    cadence="on_revision",
    environments=_ALL,
    model=ReimbReturnReasonCatalog,
    natural_key=("code",),
    rows=(
        {"code": "MISSING_OR", "label": "Missing official receipt",
         "category": "missing_doc", "promoted_check": True},
        {"code": "PER_DIEM_CALC", "label": "Per-diem miscomputed",
         "category": "wrong_amount", "promoted_check": True},
        {"code": "OBSOLETE_FORM", "label": "Obsolete / wrong form version",
         "category": "wrong_form", "promoted_check": False},
        {"code": "UNSIGNED", "label": "Missing required signature",
         "category": "no_signature", "promoted_check": False},
        {"code": "LATE_LIQUIDATION", "label": "Beyond the 30-day liquidation deadline",
         "category": "late", "promoted_check": False},
        {"code": "FARE_CLASS", "label": "Above-economy fare without certification",
         "category": "policy", "promoted_check": True},
        {"code": "OTHER", "label": "Other (see comment)",
         "category": "other", "promoted_check": False},
    ),
)


# --- Template bindings (R-5) -----------------------------------------------
# Which checklist requirement each generated form satisfies. `document_key` must
# be a key registered with core-service #8 in
# ``modules/reimbursement/documents/registry.py`` — the pair is asserted by
# test_reimb_documents.py so a rename on either side cannot ship half-done.
#
# Only `generated_doc` catalog rows appear here. CTC-47 is external_wet_sign and
# RER-46 is an upload: both are documents a HUMAN signs or supplies, so
# generating them would assert something the system cannot know.
#
# `claim_kind` is always EXPLICIT, never NULL-for-both, even though the column
# permits it and `_bindings` now honours it: a generated form is per-kind by
# construction, and the two kinds' documents share no COA appendix number. A
# NULL row is a capability the R-9 catalog editor may one day need — not a
# shortcut this seed should take.
REIMB_TEMPLATE_MAPS = SeedDataset(
    name="reimb_template_maps",
    owner="Accounting Unit / resident COA auditor",
    cadence="on_revision",
    environments=_ALL,
    model=ReimbTemplateMap,
    natural_key=("claim_kind", "checklist_code"),
    rows=(
        {
            "claim_kind": "reimbursement",
            "checklist_code": "IOT-45",
            "document_key": "reimb.iot45",
            "title": "Itinerary of Travel",
            "form_no": "GAM Vol. II, Appendix 45",
            "circular_version": _COA_CHECKLIST,
            "sort": 1,
        },
        {
            "claim_kind": "reimbursement",
            "checklist_code": "AR-01",
            "document_key": "reimb.ar01",
            "title": "Accomplishment Report",
            "form_no": None,
            "circular_version": _COA_CHECKLIST,
            "sort": 2,
        },
        {
            "claim_kind": "reimbursement",
            "checklist_code": "DV-32",
            "document_key": "reimb.dv32",
            "title": "Disbursement Voucher",
            "form_no": "GAM Vol. II, Appendix 32",
            "circular_version": _COA_CHECKLIST,
            "sort": 3,
        },
        # R-6-liq-settle. This row is what ACTIVATES the deliberately-inert
        # LR-44 catalog row seeded at R-6-liq-chain — three sessions after the
        # requirement was authored, exactly as the `deadline_check` substrate
        # waited for the rule that discharged it. Under GAM 2015 Appendix 44 is
        # the Liquidation Report (the "App 44 = Itinerary" numbering is the
        # pre-2015 NGAS scheme).
        {
            "claim_kind": "liquidation",
            "checklist_code": "LR-44",
            "document_key": "reimb.lr44",
            "title": "Liquidation Report",
            "form_no": "GAM Vol. II, Appendix 44",
            "circular_version": _COA_CHECKLIST,
            "sort": 1,
        },
    ),
)


REIMBURSEMENT_DATASETS: tuple[SeedDataset, ...] = (
    REIMB_CONFIGS,
    REIMB_DTE_CLUSTERS,
    REIMB_REGION_CLUSTERS,
    REIMB_CHECKLIST,
    REIMB_RETURN_REASONS,
    REIMB_TEMPLATE_MAPS,
)


async def apply_reimbursement_seeds(session: AsyncSession) -> list[dict[str, Any]]:
    """Idempotently upsert every reimbursement reference dataset. Returns per-dataset
    summaries. Flushes; the caller owns the commit."""
    return [await apply_dataset(session, ds) for ds in REIMBURSEMENT_DATASETS]
