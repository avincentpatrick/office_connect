# Module: CSS-IS (Client Satisfaction Survey Information System)

## 1. Status

**NOT STARTED — migration planning session pending. Phase slots: 1 (data/auth
promotion) and 8 (full migration).** The live v2.24 build stays on Hugging
Face until migrated in.

## 2. Purpose

The bureau's existing survey system (ARTA walk-in, Activity-SERVQUAL,
RP-SERVQUAL; bilingual EN+Filipino public form). Migrates onto the shared
platform store and contributes satisfaction data to the CSMR and OPCR outputs.

## 3. Source references

- `references/CSS-IS_Current_Build_Reconciliation.md` — live-build re-baseline
  (**highest migration risk: timestamps stored naive-local Manila, not UTC**;
  raw `sqlite3` storage; production AI layer `ai_core.py`; bilingual form kept)
- `references/Digital_Transformation_Integration_Blueprint.md` §6
- Promotion sources for the platform: `auth.py`, `ratelimit.py` (Phase 2),
  `rechain_audit.py` (audit chain reconciliation), `tzutil.py` (timezone).
  **The css-is repo is not in this workspace — locate it before Phase 1/2.**

## 4. Integration obligations (Blueprint §3/§6)

- `activity_id` (nullable) on Activity-SERVQUAL and RP-SERVQUAL surveys —
  survey creation gains "pick or create activity". ARTA walk-in surveys need
  no activity link (transaction-based).
- **CSMR Annex-B exporter** over CSS-IS data (ARTA MC 2022-05 as amended by
  MC 2023-05) — **operative deadline Apr 30 of the following year** (ARTA MC
  2022-01 + annual advisories; the "last working day of January" in older
  texts is superseded — keep configurable). Sections V/VI require persisting
  the prior year's action plan.
- **Harmonized CSM instrument as versioned config** (research —
  `docs/research/round2/arta-csm-foi-nap-records.md`): CC1–CC3 with skip logic
  (CC2/CC3 only when CC1 ∈ 1–3), verbatim SQD0–SQD8 + N/A options; scoring =
  **(Strongly Agree + Agree) ÷ (responses excluding N/A) × 100**, SQD0
  reported separately; MC 2023-05 interpretation bands as data (Poor <60 ·
  Fair 60–79.9 · Satisfactory 80–89.9 · VS 90–94.9 · Outstanding 95–100).
- **Internal services are in CSM scope**: platform transactions (reimbursement
  paid, booking completed, document released) trigger survey invitations via a
  Citizen's-Charter service catalog (internal/external tagged) — the catalog
  doubles as the CC source of truth (handbook generation, Certificate of
  Compliance support).
- Naive-Manila → UTC timestamp conversion during data migration
  (per-table-class per the reconciliation doc); audit re-chain; `storage.py`
  rewritten onto async SQLAlchemy.
- CSS-IS resource persons / external participants merge into **`core_contacts`**
  (shared with DTWIS — Rule 10; delta to record at migration).

## 5. Open decisions

- Table namespace mapping for migrated data (`css_*` per DB standards §2,
  pluralized).
- AI layer (`ai_core.py`, Gemini/Groq) promotion to shared platform service
  (author decision recorded in the reconciliation doc §5: promote).

## 6. Plan

*(Filled at the module's requirements/migration session.)*
