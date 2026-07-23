"""Reference-data seed datasets — the actual rows loaded by the seed framework.

Each dataset names its **owner** (who keeps it current) and **cadence** (how often
the upstream source changes), per master-plan §2. External datasets:
- PH holidays — refreshed **annually** from the holiday proclamations.
- PSGC region map — **quarterly** (feeds DTE clusters; loaded from Stage C).
- GRDS / peso thresholds — **on revision**.
Reference data loads in every environment (it is public law/config, not synthetic
fixtures — those stay non-prod in ``bootstrap load-fixtures``).
"""

from __future__ import annotations

from datetime import date

from office_connect.core.models import (
    ActivityTag,
    ComplianceDeadline,
    Holiday,
    ObjectCode,
    PapCode,
)
from office_connect.core.seeds.base import SeedDataset
from office_connect.core.seeds.rbac import PERMISSIONS_DATASET, ROLES_DATASET

_ALL = ("all",)
_FY = date(2026, 1, 1)

# --- Activity taxonomies (GAD/CCET/DRR/UHC) -------------------------------
ACTIVITY_TAGS = SeedDataset(
    name="activity_tags",
    owner="GAD Focal Point / Planning Unit",
    cadence="on_revision",
    environments=_ALL,
    model=ActivityTag,
    natural_key=("taxonomy", "code"),
    rows=(
        {"taxonomy": "gad", "code": "attributed", "label": "GAD-attributed", "sort_order": 1},
        {"taxonomy": "gad", "code": "targeted", "label": "GAD-targeted (direct)", "sort_order": 2},
        {"taxonomy": "gad", "code": "mainstreamed", "label": "GAD-mainstreamed", "sort_order": 3},
        {"taxonomy": "ccet", "code": "adaptation", "label": "Climate Change Adaptation", "sort_order": 1},
        {"taxonomy": "ccet", "code": "mitigation", "label": "Climate Change Mitigation", "sort_order": 2},
        {"taxonomy": "drr", "code": "prevention_mitigation", "label": "DRR: Prevention & Mitigation", "sort_order": 1},
        {"taxonomy": "drr", "code": "preparedness", "label": "DRR: Preparedness", "sort_order": 2},
        {"taxonomy": "drr", "code": "response", "label": "DRR: Response", "sort_order": 3},
        {"taxonomy": "drr", "code": "rehabilitation_recovery", "label": "DRR: Rehabilitation & Recovery", "sort_order": 4},
        {"taxonomy": "uhc", "code": "service_coverage", "label": "UHC: Service Coverage", "sort_order": 1},
        {"taxonomy": "uhc", "code": "financial_protection", "label": "UHC: Financial Protection", "sort_order": 2},
    ),
)

# --- UACS object codes (travel = 5-02-01-010-00) --------------------------
OBJECT_CODES = SeedDataset(
    name="object_codes",
    owner="Budget / Accounting Unit",
    cadence="on_revision",
    environments=_ALL,
    model=ObjectCode,
    natural_key=("uacs_object_code", "effective_from"),
    rows=(
        {"uacs_object_code": "5-02-01-010-00", "title": "Traveling Expenses - Local", "effective_from": date(2020, 1, 1)},
        {"uacs_object_code": "5-02-01-020-00", "title": "Traveling Expenses - Foreign", "effective_from": date(2020, 1, 1)},
        {"uacs_object_code": "5-02-02-010-00", "title": "Training Expenses", "effective_from": date(2020, 1, 1)},
        {"uacs_object_code": "5-02-03-010-00", "title": "Office Supplies Expenses", "effective_from": date(2020, 1, 1)},
    ),
)

# --- PREXC skeleton (illustrative top-level nodes; agency GAA fills the tree) ---
PAP_CODES = SeedDataset(
    name="pap_codes",
    owner="Planning & Budget Unit",
    cadence="annual",
    environments=_ALL,
    model=PapCode,
    natural_key=("fiscal_year", "uacs_code"),
    rows=(
        {"fiscal_year": 2026, "uacs_code": "100000100001000", "level": "cost_structure",
         "title": "General Administration and Support (skeleton)", "effective_from": _FY},
        {"fiscal_year": 2026, "uacs_code": "300000100001000", "level": "cost_structure",
         "title": "Operations (skeleton)", "effective_from": _FY},
    ),
)

# --- PH holidays 2026 (regular + special non-working; movable Islamic dates
#     are added by proclamation later — annual cadence) ---------------------
_PROC = "PH Holiday Proclamation (FY2026)"
HOLIDAYS = SeedDataset(
    name="holidays_2026",
    owner="HR / Admin (annual holiday proclamations)",
    cadence="annual",
    environments=_ALL,
    model=Holiday,
    natural_key=("calendar_date", "name"),
    rows=(
        {"calendar_date": date(2026, 1, 1), "name": "New Year's Day", "holiday_type": "regular", "proclamation_ref": _PROC},
        {"calendar_date": date(2026, 2, 17), "name": "Chinese New Year", "holiday_type": "special_non_working", "proclamation_ref": _PROC},
        {"calendar_date": date(2026, 4, 2), "name": "Maundy Thursday", "holiday_type": "regular", "proclamation_ref": _PROC},
        {"calendar_date": date(2026, 4, 3), "name": "Good Friday", "holiday_type": "regular", "proclamation_ref": _PROC},
        {"calendar_date": date(2026, 4, 4), "name": "Black Saturday", "holiday_type": "special_non_working", "proclamation_ref": _PROC},
        {"calendar_date": date(2026, 4, 9), "name": "Araw ng Kagitingan", "holiday_type": "regular", "proclamation_ref": _PROC},
        {"calendar_date": date(2026, 5, 1), "name": "Labor Day", "holiday_type": "regular", "proclamation_ref": _PROC},
        {"calendar_date": date(2026, 6, 12), "name": "Independence Day", "holiday_type": "regular", "proclamation_ref": _PROC},
        {"calendar_date": date(2026, 8, 21), "name": "Ninoy Aquino Day", "holiday_type": "special_non_working", "proclamation_ref": _PROC},
        {"calendar_date": date(2026, 8, 31), "name": "National Heroes Day", "holiday_type": "regular", "proclamation_ref": _PROC},
        {"calendar_date": date(2026, 11, 1), "name": "All Saints' Day", "holiday_type": "special_non_working", "proclamation_ref": _PROC},
        {"calendar_date": date(2026, 11, 30), "name": "Bonifacio Day", "holiday_type": "regular", "proclamation_ref": _PROC},
        {"calendar_date": date(2026, 12, 8), "name": "Feast of the Immaculate Conception", "holiday_type": "special_non_working", "proclamation_ref": _PROC},
        {"calendar_date": date(2026, 12, 24), "name": "Christmas Eve", "holiday_type": "special_non_working", "proclamation_ref": _PROC},
        {"calendar_date": date(2026, 12, 25), "name": "Christmas Day", "holiday_type": "regular", "proclamation_ref": _PROC},
        {"calendar_date": date(2026, 12, 30), "name": "Rizal Day", "holiday_type": "regular", "proclamation_ref": _PROC},
        {"calendar_date": date(2026, 12, 31), "name": "Last Day of the Year", "holiday_type": "special_non_working", "proclamation_ref": _PROC},
    ),
)


def _deadline(code, name, authority, cadence, due_rule, *, wd=True):
    return {
        "code": code,
        "name": name,
        "authority": authority,
        "cadence": cadence,
        "due_rule": due_rule,
        "use_working_day_math": wd,
        "tenant_id": None,
        "effective_from": _FY,
    }


# --- Consolidated statutory calendar (master-plan §3.4) -------------------
COMPLIANCE_DEADLINES = SeedDataset(
    name="compliance_deadlines",
    owner="Compliance / QMS Focal Point",
    cadence="on_revision",
    environments=_ALL,
    model=ComplianceDeadline,
    natural_key=("code", "effective_from", "tenant_id"),
    rows=(
        _deadline("csmr_to_arta", "CSMR to ARTA", "ARTA MC 2022-05/2023-05, MC 2022-01",
                  "annual", {"kind": "fixed_date", "month": 4, "day": 30, "note": "operative; configurable"}),
        _deadline("foi_registry", "FOI Registry + Agency Info Inventory", "FOI MC 1 & 5 s.2017",
                  "quarterly", {"kind": "quarterly_plus_annual_summary"}),
        _deadline("bar_far_quarterly", "BAR 1 + FAR 1/1-A/1-B/(1-C)/2/2-A/5/6", "COA-DBM JC 2019-1",
                  "quarterly", {"kind": "days_after_quarter", "days": 30}, wd=False),
        _deadline("far4_monthly_disbursements", "FAR 4 (Monthly Disbursements)", "COA-DBM JC 2019-1",
                  "monthly", {"kind": "day_of_following_month", "day": 10}, wd=False),
        _deadline("far3_aging_ddo", "FAR 3 (Aging of Due & Demandable Obligations)", "COA-DBM JC 2019-1",
                  "annual", {"kind": "days_after_year_end", "days": 30}, wd=False),
        _deadline("bed_1_4", "BED 1-4", "annual DBM Circular Letter",
                  "annual", {"kind": "fixed_month", "month": 11, "note": "mid-November per per-year CL"}),
        _deadline("final_app", "Final APP (HoPE-approved + Certificate of Posting)", "RA 12009 IRR §7.7.5",
                  "annual", {"kind": "fixed_month", "month": 1, "note": "end of January"}),
        _deadline("updated_app", "Updated APP", "GPPB-TSO advisory",
                  "semiannual", {"kind": "semiannual", "months": [7, 1], "note": "end-July / end-January"}),
        _deadline("app_cse_mphilgeps", "APP-CSE -> mPhilGEPS", "DBM CL 2011-6",
                  "annual", {"kind": "fixed_date", "month": 8, "day": 31, "note": "of prior year, per PS-DBM advisory"}),
        _deadline("pmr", "Procurement Monitoring Report (PMR)", "RA 12009 IRR §42.1(k)",
                  "semiannual", {"kind": "semiannual", "months": [7, 1], "note": "end-July / end-January"}),
        _deadline("rpci_rpcsp", "RPCI / RPCSP", "GAM; COA 2020-006",
                  "semiannual", {"kind": "fixed_dates", "dates": ["01-31", "07-31"]}),
        _deadline("rpcppe", "RPCPPE", "GAM Appendix 73",
                  "annual", {"kind": "fixed_date", "month": 1, "day": 31}),
        _deadline("pif_gsis_coa", "PIF -> GSIS + COA", "COA 2018-002 / RA 656",
                  "annual", {"kind": "fixed_date", "month": 4, "day": 30}),
        _deadline("po_copies_coa", "PO copies -> COA", "COA 2009-001",
                  "per_event", {"kind": "working_days_from_event", "working_days": 5, "event": "issuance"}),
        _deadline("year_end_fs_coa", "Year-end FS + schedules -> COA", "GAM Vol I",
                  "annual", {"kind": "fixed_date", "month": 2, "day": 14}),
        _deadline("spms_ladder", "SPMS ladder (targets, ratings, Form 5, IDPs)", "DOH DO 2019-0440 Annex A",
                  "custom", {"kind": "date_ladder", "note": "Jan/Jul ladder"}),
        _deadline("gad_ar", "GAD Accomplishment Report (via GMMS)", "PCW-DBM-NEDA JMC 2022-01",
                  "annual", {"kind": "fixed_month", "month": 1}),
        _deadline("npc_registration_renewal", "NPC registration renewal", "NPC Circular 2022-04",
                  "annual", {"kind": "before_expiry", "days": 30}),
        _deadline("iso_surveillance", "ISO surveillance / recertification", "certification body / GQMC-PBB",
                  "annual", {"kind": "per_certification_body"}),
        _deadline("liquidation_clocks", "Liquidation clocks", "COA 97-002 / EO 77",
                  "per_event", {"kind": "days_from_event", "days": 30, "event": "cash advance return"}, wd=False),
        _deadline("par_ics_renewals", "PAR/ICS renewals", "GAM / COA 2022-004",
                  "custom", {"kind": "every_n_years", "years": 3, "per": "slip"}),
        _deadline("transparency_seal", "Transparency Seal postings", "GAA General Provisions",
                  "custom", {"kind": "per_item_checklist"}),
    ),
)

# Registry order matters only for readability; each dataset is independent.
# The RBAC catalogs (permissions, roles) are public config — they load in every
# environment; the role→permission GRANTS are wired by ``core/seeds/rbac.py``
# (bespoke resolver, run via ``bootstrap seed-rbac``), not as a SeedDataset.
REGISTRY: tuple[SeedDataset, ...] = (
    ACTIVITY_TAGS,
    OBJECT_CODES,
    PAP_CODES,
    HOLIDAYS,
    COMPLIANCE_DEADLINES,
    PERMISSIONS_DATASET,
    ROLES_DATASET,
)
