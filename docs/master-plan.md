# Office-Connect — Master Plan v1

**Adopted:** 2026-07-23 · **Status:** authoritative build plan
**Supersedes for sequencing:** the phase list in `references/OfficeConnect_Build_Execution_Plan_v1_0.docx` (which stays read-only and unamended, per repo rules)
**Precedence:** standing rules → `docs/standards/` → this plan → `references/` module specs → the `.docx` (scope detail only)

This document consolidates, into one authoritative plan:

1. The 11-phase execution plan (`.docx`) **plus** the five amending references that
   were never folded back into it (reimbursement-first per `Phased_Rollout_Assessment.md`
   §0.1; Windows-Server hosting per `Hosting_Target_Clarification.md`; CSS-IS drift per
   `CSS-IS_Current_Build_Reconciliation.md`; the data-spine amendments per
   `Digital_Transformation_Integration_Blueprint.md`; dependency analysis per
   `Reimbursement_First_Dependency_Analysis.md`).
2. Two deep-research rounds (18 digests in `docs/research/` — engineering best
   practices + Philippine legal/regulatory standards), including a **corrections
   ledger** (§5) where research disproved reference content.
3. Five owner-added modules (2026-07-22): connected **Calendar of Activities**,
   **Controlled Document Management**, **Supply Management**, **WFP + PPMP crafting**,
   **Performance & Deliverables** (IPCR/OPCR/DPCR/SPCR, accomplishment reports, Risk
   Registry, Management Review, BED, BAR) — and the rename **DMWIS → Document
   Tracking & Workflow IS (DTWIS)** to avoid conflict with document *management*.
4. The owner's binding connectedness directive (§1).

---

## 1. Platform thesis & connectedness contract

> Owner directive (2026-07-22, binding): *"Make sure everything is connected to each
> other. Workflow is important to this application. I don't want it patched. Each
> module must be connected to relevant modules. It must not be duplicative."*

**Thesis** (from the Blueprint, now elevated): *reports are byproducts of work.* Every
mandated government output must be **generated** from operational data, never
compiled by hand. Connectedness is enforced structurally, not aspirationally:

- **One workflow engine.** Every approval/routing flow in the platform runs on the
  shared core engine (§1.1 item 1): reimbursement claims and liquidations, DTWIS
  document routing and signatures, QMS document change requests, supply requisitions
  and disposals, PPMP/WFP submission→consolidation→approval, SPMS commitment and
  rating sign-off chains. **No module builds its own approval machinery.** This
  supersedes the reference spec's "build module-internal, reconcile later" approach
  (owner decision, 2026-07-22).
- **One instance of every shared capability**, owned by `core` (§1.1). Modules
  consume via service interfaces; they never re-implement and never import each other
  (`lint-imports` enforced).
- **A connection spine** of shared keys (§1.2): `core_activities` (+ tags),
  `core_pap_codes`/`core_object_codes` (UACS/PREXC), staff directory + org units,
  document/attachment references. All cross-module links are nullable/soft and
  backfillable; joins go through spine keys only; no cross-module writes.
- **A reviewable connection matrix** (§1.3). Every declared link becomes one
  cross-module integration test at SIT (Stage I).

### Rule 10 (standing rule, locked 2026-07-23)

> **Shared service first.** Before any module adds a table, service, or engine,
> check the core-services registry (§1.1). If an equivalent exists, consume it.
> Duplication requires a documented waiver in the module doc's delta register.

### 1.1 Core-services registry (the anti-duplication list)

| # | Core service | What it owns | Consumers |
|---|---|---|---|
| 1 | **Workflow engine** (`core_workflow_*`) — **SHIPPED 2026-07-27 (Stage C, migration `0012`; contract: `docs/standards/workflow-standards.md`)** | Versioned **immutable** definitions (instances pinned to their version), states, transitions with typed guards (`min_amount`/`max_amount`, `required_permission`, `requires_comment` — no free-form DSL; authorizes on permission STRINGS via `authorize_scoped`, `required_role_id` reserved unwired), per-instance step rows with `join_type` (all/any/quorum, fan-in scoped to `revision_no`), append-only **audited** event log (derived `current_state` + replay test), delegation/OIC with on-behalf-of recording (**`core_workflow_delegations`** — refines B3; see below), compare-and-swap transitions (409 on race) + idempotency keys, SELECT FOR UPDATE fan-in, SLA sweeps (idempotent, non-interrupting reminders). Flag OFF blocks **new** instances only — in-flight always finishes. | reimb, dtwis, qms, supply, plan, perf, admin |
| 2 | **Attachments & files** (`core_attachments`) | Stream-capped upload → magic-byte allowlist (JPEG/PNG/WebP/PDF; HEIC→JPEG; never SVG) → SHA-256 → content-addressed volume store → ClamAV scan (fail-closed) → Pillow re-encode/EXIF-strip. Auth-checked streaming downloads only (no static mounts). `retention_class`/`retain_until`/`legal_hold` columns. | all modules |
| 3 | **Frozen-snapshot signatures** — **SNAPSHOT HALF SHIPPED 2026-08-04 (Stage C R-5-gen; `core/documents/snapshots.py` + `core_document_snapshots`, migration `0018`)** | Export→PDF→SHA-256→snapshot+identity+timestamp; "modified after signature" re-flag (reference §19.8, promoted to core). **Shipped:** freeze/supersede/void over the polymorphic `(subject_kind, subject_id)` key, two hashes (`content_sha256` over the bytes = tamper evidence; `source_fingerprint` over the canonical render context = change detection, because PDF bytes embed a creation timestamp and could never answer "did the data move?"), and `stale_snapshots()` as the re-flag — which **reports and never voids**, since whether a divergence invalidates a signature is a workflow decision. `superseded` (ordinary reissue) is kept distinct from `voided` (inputs changed) because that distinction is what an auditor is actually looking for. **Deferred to R-6:** signature CAPTURE — certification steps A/B/C and external wet-sign — which needs the liquidation chain and the signatory config still open with the resident COA auditor. | reimb, dtwis, qms, perf |
| 4 | **Notifications** | Outbox table + retry, SMTP/Gmail drivers, in-app bell + notification center, WebSocket via Redis Pub/Sub + 30 s poll fallback, per-user prefs. Modules emit events only. | all modules |
| 5 | **Reference numbers** — **SHIPPED 2026-07-27 (Stage C R-1; `core/reference_numbers.py` + `core_reference_sequences`)** | `XX-YYYY-NNNN`, pluggable sequences per form type / fund cluster / year, never reused, voids retained. | all modules |
| 6 | **Holiday & work-suspension calendar** | PH national/local holidays + "walang pasok" suspensions per year; the single working-day math engine for **every** deadline (FOI, COA, ARTA, SPMS, liquidation, RA 11032 tiers). | all deadline engines |
| 7 | **Checklist / documentary-requirements engine** — **SHIPPED 2026-08-03 (Stage C R-3; `core/checklist/` — pure grammar/checks/reconciliation over dataclasses, storage stays with the consumer; promote to `core_checklist_*` tables at Stage E when DTWIS becomes consumer #2)** | Generalized from the reimbursement spec: `required_rule` JSONB grammar + `auto_checks` (file_present, amount_threshold, date_within_trip, sum_matches, keyword_absent(OCR), deadline_check) — **four live at R-3; `deadline_check` went live at R-6 with the liquidation clock. `keyword_absent` waits on OCR — re-deferred at R-9 from Stage C to **Stage H**, since build spec §14's R-9 row never asked for it and adding Tesseract + an extraction stage to a hardening/gate session would have been scope for its own sake. Registered and returning a named `skipped` rather than a silent pass, with no seeded rule using it**. Flags never block alone; missing required items block transitions (submit / resubmit / approve — never return or cancel, which would trap the item). Catalog versions pinned to the issuing circular revision. | reimb (first), dtwis, qms, supply, plan |
| 8 | **Template → PDF generation** — **SHIPPED 2026-08-04 (Stage C R-5-gen; `core/documents/` — engine only, consumers register their own templates)** | WeasyPrint in Celery (never in request path; never wkhtmltopdf), Jinja2 + design tokens, print-faithful government forms (GAM appendices, DOH-SPMS forms, GPPB forms, NAP forms), XLSX-first for DBM/COA matrix annexes; outputs stored as immutable snapshot attachments (hash in audit chain). **Shipped:** a registry a consumer registers template dirs + `DocumentSpec`s into (the inversion that keeps `core → modules` impossible), an autoescape-on / `StrictUndefined` Jinja environment, a print stylesheet built from `core/ui/tokens.py` so PDFs inherit tenant branding with no raw hex, an **injectable** `PdfRenderer` (WeasyPrint lazy-imported inside it, so core imports and the test suite run on a Windows host with no Pango), and the `register_enqueuer` seam ops injects Celery through. Outputs ride core-service #2 with `origin='generated'`. **Deferred:** XLSX annexes (no consumer yet); ReportLab for millimetre-exact overlays (add per-template if a form ever demands it). | all modules |
| 9 | **Search** | PostgreSQL FTS (tsvector + pg_trgm), soft-delete- and scope-aware; OCR text of scanned attachments indexed. **Not the landing query bar** — that is a deterministic matcher over `NAV_GROUPS` labels + `intent_keywords` (shipped Stage D-1): browser-side, no index, no records, no server call. §1.3's `landing/query bar → all` row says it — *routing only*. A future field that searches RECORDS is a consumer of this service and a separate design (`docs/modules/landing.md` §6b). | all modules |
| 10 | **Report lineage** | Every generated report records source filter + config version + generated-by/at; archived copy. | reports, all generators |
| 11 | **Compliance-deadline calendar** (`core_compliance_deadlines`) | Every statutory deadline in §3.4 as effective-dated, tenant-overridable data; feeds the Government Outputs screen and reminder ladders. | reports, all modules |
| 12 | **External contacts** (`core_contacts`) | ONE registry merging the DTWIS contacts directory and CSS-IS resource persons/external participants (dedup decision — delta recorded in both module docs). | dtwis, css, admin |
| 13 | **Document-type / signatory-config / template-map taxonomy** | One registry (types, Google-Docs/PDF template links, signatory chains, wet-signature flags) consumed by DTWIS, reimbursement, and QMS — the references specified this separately in §19.7 and `reimb_signatory_config`; unified here. | dtwis, reimb, qms |
| 14 | **Staff directory + org units** | Plantilla-authoritative person registry + self-referencing `core_org_units`; modules join, never copy. | all modules |
| 15 | **Activity spine** | `core_activities` (+ `core_activity_tags` for GAD / CCET climate / DRR / UHC — configurable taxonomies, never boolean columns) + `core_pap_codes` (per-FY PREXC tree: cost structure → OO → program → subprogram → activity/project; UACS never-reuse/deactivate semantics; year-rollover re-mapping wizard) + `core_object_codes` (10-digit UACS; travel = 5-02-01-010-00). | everything (§1.2) |
| 16 | **AI service** | CSS-IS `ai_core` promoted (Gemini + Groq fallback, DB-backed budget, audit tables reconciled with the query log). **The Stage D-1 query bar is deterministic and has NO `ai_core` dependency** — it becomes a consumer only if a later increment adds natural-language intent. `ai_core` is its own Stage D increment (D-4). | query bar *(only if NL intent ships)*, css, later modules |
| 17 | **Calendar composition** (`core/calendar/`) — **SHIPPED 2026-08-09 (Stage D-2; contract: `docs/standards/api-standards.md` §9k)** | The registry that lets ONE agenda surface read many modules without any of them importing each other. Core owns the `CalendarEvent` value type, the `CalendarSource` dataclass, `register_source()` and the merge/window/day-grouping; each module implements a source where its OWN scope rule is a local import; `main.py` registers them. Every source declares the NAME of the rule it applies (`register_source` refuses an empty one) and may carry a feature flag — a flag-OFF source is **absent**, not empty. **Not the same thing as #11** (`core_compliance_deadlines` is *data*; this is *composition*) and **not #6** (`core/workdays` is the date math this consumes). A second calendar-shaped surface reads this registry; it never grows its own fan-out. | reimb (travel + liquidation), admin (bookings), dtwis (document deadlines), perf (SPMS dates), reports |

### 1.2 The connection spine

**`core_activities` is the Calendar of Activities hub** — the answer to "what work
was this for?". Everything links to it (nullable, backfillable):

- travel claims (`reimb_claims.activity_id`) → travel spend per activity/PPA is a query
- room bookings (`admin_*`), DTWIS documents (multi-tag), CSS surveys (Activity- and
  RP-SERVQUAL), WFP lines (via `ppa_code`), IPCR/OPCR accomplishment items (MOVs),
  TA deployments (future), calendar events with **cash-advance liquidation countdowns**
  (COA 97-002 clocks surface on the event that spent the money)
- roll-up path: activity → PAP → subprogram → program → cost structure (BED/BAR shape)

**PPA/UACS codes** tie planning to execution to reporting: WFP line → PPMP line →
obligation/disbursement events → BAR 1 / FAR columns → OPCR actuals → Government
Outputs. **Staff/org units** scope every approval ("Division Chief OF division X")
and every rating chain.

### 1.3 Connection matrix (each row = one declared link = one SIT test)

| From → To | Key / service | Direction & nature |
|---|---|---|
| reimb → core_activities | `activity_id` | claim tagged to activity ("pick or create" in wizard step 1) |
| reimb → DTWIS | `dpo_no` (natural) + `dpo_document_id` (FK, DPO backfill task at Stage E) | soft ref hardened later |
| reimb → plan | `pap_code_id` + object code 5-02-01-010-00 on claims | travel spend feeds WFP utilization & BAR |
| reimb → calendar | **IMPLEMENTED Stage D-2** as two registered `CalendarSource`s (§1.1 #17), not a join: `reimb.travel` (scoped by `oversight_scope` ∪ own) + `reimb.liquidation` (own advances only). The countdown reads **`reimb_cash_advances.deadline_date`**, never `reimb_claims.liquidation_deadline` — that column is a mirror, and feeding both would draw two clocks for one obligation | derived badge |
| dtwis → core_activities | multi-tag `activity_id` | documents grouped per activity |
| dtwis → core_contacts | sender/recipient FKs | one external-contacts registry |
| dtwis → qms | tracked doc may cite controlled-document code | reference only |
| css → core_activities | `activity_id` on Activity/RP-SERVQUAL | ARTA walk-in needs none |
| css ← all modules | CSM trigger on completion of any internal-service transaction (reimb paid, booking done, document released) | per Citizen's Charter service catalog |
| qms ← css/dtwis/reimb/perf/supply | Management-Review input pack auto-pull (9.3.2: CSM scores, audit results, KPIs, NC/CAPA, risk actions, resource flags) | read-only aggregation, frozen on conduct |
| qms ← perf | COA audit findings (AOM/NS/ND/NC) feed Risk Registry + MR inputs | event feed |
| supply → plan | PR line must reference approved APP line (soft/manual until W2-A ships) | IRR §7.8 guard |
| supply → core (staff) | custodian accountability ledger (PAR/ICS per employee) | clearance/PTR/bonding views |
| plan → core_pap_codes / object codes | WFP + PPMP lines keyed to PAP + UACS object code | tie-out validations |
| perf → plan | OPCR/DPCR targets pull from WFP/BED lines (never retyped) | MP dependency W2-C←W2-A |
| perf → core_attachments | MOV per rated line item ("no proof → not rated") | hard rule |
| admin → core_activities | `activity_id` nullable on bookings; bookings feed Calendar of Activities output | spine |
| reports ← everything | read-only KPI + Government Outputs generators + lineage | no writes |
| landing/query bar → all | NAV_GROUPS intents incl. report intents | routing only |

Integration invariants (binding, from the Blueprint): no cross-module writes; joins
through spine keys only; every cross-module link nullable/soft; every report
lineage-traceable.

---

## 2. Stage sequence (Build Track)

Strategy: unchanged foundation-floor logic (Phases 0–2 before anything user-facing),
reimbursement-first (locked decision), then platform surfaces, then the two big
document modules, then convergence/reporting, then hardening + pilot. The five new
modules that have hard annual government cycles but do not block the pilot ship as
**Wave 2** behind fail-safe-OFF flags, each with its own R-0-style requirements gate.

| Stage | Old phase | Scope (headline) | Exit gate |
|---|---|---|---|
| **A** | 0 (inc 2–4) | Ops + integrations + spine amendments | phase-0 QA green, tag pushed |
| **B** | 2 | Identity & access (auth/RBAC/directory) | one-login gate |
| **C** | R-0…R-9 | Reimbursement vertical + core workflow engine + first React shell | R-9 gate, flag ON for pilot cohort |
| **D** | 3 | Landing shell, query bar, **Calendar surface**, AI service | shell QA |
| **E** | 4–7 | **DTWIS** (renamed from DMWIS) | documents-only pilot |
| **F** | new | **QMS module** (controlled docs + risk + MR + NC/CAPA) | ISO-evidence QA |
| **G** | 1+8 | CSS-IS convergence (PG migration + React + ARTA v2023) | parity + score-identity QA |
| **H** | 9 | Admin + unified Reports + **Government Outputs** | cross-module drill-down QA |
| **I** | 10 | Legacy migration, sync, hardening, SIT, **pilot gate** | pilot exit criteria |
| **W2-A** | new | Planning & Budget (WFP/BED/BAR + PPMP/APP) | own R-0 + QA gate |
| **W2-B** | new | Supply Management | own R-0 + QA gate |
| **W2-C** | new | Performance & Deliverables (SPMS + COA findings) | own R-0 + QA gate |

### Stage A — Foundation completion (Phase 0, increments 2–4)

- **Increment 2 (ops)** — revised from `foundation.md` §3: deploy guard script;
  scheduled `pg_dump -Fc` backups with **3-2-1 placement** (off-VM copy + periodic
  offline copy) and **one proven restore** (restore drill also runs `verify_chain()`
  over the audit log — free integrity check); Celery worker + first beat task;
  **migration as an explicit deploy step** (migration-on-boot demoted to dev-only,
  env-gated — multi-worker boot races and crash-loop DDL are a known prod failure
  mode); **provision the private git remote OFF the future production hardware**
  (the repo + Alembic history is a DR artifact).
- **Increment 3 (integrations)** — storage driver abstraction (Drive vs local volume
  is a deployment-time decision, see §4), SMTP+Gmail email drivers behind the
  notification outbox, bootstrap CLI + synthetic fixtures, design-token contract via
  `/api/v1/config`.
- **Increment 4 (spine amendments — NEW)** — `core_activities` + `core_activity_tags`;
  `core_pap_codes` + `core_object_codes` skeletons (per-FY, effective-dated);
  holiday/suspension calendar; `core_compliance_deadlines`; attachments service;
  notification outbox tables; report-lineage table; seed framework (idempotent,
  environment-aware; owners + cadence for external datasets — PSGC quarterly, holiday
  proclamations annually, GRDS/threshold revisions); `docs/compliance/` +
  `docs/operations/` scaffolds; API-versioning + observability standards (structured
  JSON logs with request IDs, self-hosted error tracker in compose).

### Stage B — Identity & access (Phase 2)

Auth: Redis server-side sessions (opaque ID, HttpOnly/Secure/SameSite cookie, ID
regeneration at login, revoke-all on password change/deactivation), Argon2id,
NIST 800-63B-4 password policy (length 12+ + blocklist; **no composition rules, no
forced rotation** — the reference's "letter+number" recorded as a deviation),
throttle-not-lockout (reference agrees), custom-header CSRF, break-glass local admin,
TOTP MFA for approver/admin roles (NPC Circular 2023-06 requires MFA for
personal-data access). RBAC: permission strings (never role names in code),
role→permission tables, **org-unit-scoped grants** on `core_user_roles`
(`org_unit_id` nullable = global). Staff directory: **greenfield core tables seeded
by CSV import from a CSS-IS export** — no code dependency on the CSS-IS repo (full
reconciliation stays Stage G). Delegation/OIC table (time-boxed, on-behalf-of).
Maker-checker infrastructure: DB-level pairwise-distinct checks for DV Boxes A/B/C
(COA 92-389, NGICS). Read-only **auditor role** (COA Res. 2020-034) + per-record
human-readable timeline + printable chain-verification report. Query-log middleware;
the deferred `*_by`/`division_id`/`section_id` FKs land in one migration. Audit
payload policy decision executes here (§4).

### Stage C — Reimbursement vertical (R-0…R-9) + core workflow engine

Per `references/Reimbursement_Module_Build_Spec_v1.md` **plus** the corrections
ledger (§5) and research hardening — full detail in `docs/modules/reimbursement.md`:

- **R-0**: the five author decisions, now reframed by research: EO 77 is a
  **3-cluster DTE by destination region** (I ₱1,500 / II ₱1,800 / III ₱2,200) —
  the config pack becomes effective-dated `reimb_dte_clusters` + PSGC region map.
  Plus: per-day host-provided lodging/meals flags (strip 50%/30%), gov-vehicle flag
  per leg (suppresses fare), 50-km rule with overnight-stay attestation,
  excess-claim certification path, affidavit-of-loss hard block for lodging ORs,
  CA hard-block while one is unliquidated (PD 1445 §89 — DB constraint, not a
  warning), Revised-IoT versioning on deviation, checklist catalog versioned to
  **COA Circular 2023-004**, physical-document custody states (scan → original to
  Accounting → COA), **e-signature decision with the resident COA auditor**
  (RA 8792 / COA 2021-006; default: printed form + wet ink remains the record).
- **R-2**: first React surface — **app shell + design tokens + component library
  seed (TaskList, StatusTag, ErrorSummary, wizard/stepper)** land here
  (ui-standards §7 fill-trigger). Claimant flows one-thing-per-page; approver/admin
  screens denser (GOV.UK internal-use guidance). Check-your-answers + confirmation
  pages; server-side save-and-return; directory prefill (WCAG 2.2 §3.3.7).
  **R-2-shell shipped 2026-07-28 (session 14)** — the `web/` SPA, 6 templates, the
  inventory seed, the token pipeline. **R-2-wizard shipped 2026-07-30 (session 16)**
  — the module's FIRST HTTP surface (9 endpoints under `/api/v1/reimbursement`
  behind the new `require_feature`→404 gate; conventions = api-standards §9), the
  4-step claim wizard (Documents step → R-3, module-doc delta) with submit-per-step
  save-and-return + check-your-answers + RB- confirmation, server-side directory
  prefill, and the **My-Work inbox** as the module landing; inventory grew to 17
  (Form-field family, SummaryList, ConfirmationPanel, WorkItemRow). The claimant
  journey is live end to end; the approver surface (approval screen + return dialog
  + action endpoints) completed R-4's UI half in session 17.
- **R-4**: the **shared core workflow engine** ships here (owner decision) and the
  reimbursement chain becomes its first definition. Sequential now; `join_type`
  ready for DTWIS parallel routing. **Engine CORE shipped 2026-07-27 (session 11**,
  ahead of R-4-app — pure `core_workflow_*`, migration `0012`, `docs/standards/workflow-standards.md`);
  **R-4-app shipped 2026-07-29 (session 15)** — the `reimbursement.claim` definition v1
  (spec §5.5 role chain; amount tiers deferred to an authored v2 pending DOH DO
  2019-0225 — module doc delta register), the claim lifecycle service (atomic submit:
  totals + `RB-` ref + instance + denormalized status/holder/next-action sync),
  working-day SLA stamping + escalation delivery + the repeating holder-only ladder
  via `register_sla_enqueuer` + `ops.reimb_sla_reminders`, bootstrap `seed-workflows`,
  migration `0015`. **Scope note (2026-07-29): the My-Work inbox moved to R-2-wizard**
  — it is an HTTP/UI surface and the wizard owns the module's first HTTP surface.
  **R-4-screens shipped 2026-08-03 (session 17)** — the approver surface, completing
  R-4's UI half: per-action `/approve` + `/return` endpoints on a SECOND, deliberately
  **un-gated** module router (the flag gates a module's surface but never a decision on
  an in-flight instance — api-standards §9a, workflow-standards §9), ≥1-taxonomy-reason
  enforcement in `claim_action`, the per-actor action set + CAS `row_version` + the
  spec §6.3 SLA badge embedded in `ClaimDetail`, the claim-tracker timeline +
  return-reason taxonomy endpoints, and — Rule 10, in core so every module inherits it —
  `available_actions` now filtering the actor-dependent gate guards so the UI is never
  offered a button certain to 409 (workflow-standards §3). FE: the phone-first decision
  bar folded into `/claims/:id` on a new sticky `DetailPage.actions` slot, the return
  dialog on two new inventory components (ChipGroup + FormDialog), the tracker, and
  My-Work urgency chips. No migration — head stays `0016`. A claim is now drivable to
  `paid_closed` over HTTP, so the chain is end-to-end testable for the first time.
  **Delegation decision (2026-07-27):** on-behalf-of uses a dedicated
  `core_workflow_delegations` table — this refines the Stage-B B3 "no RBAC delegation
  table" note (a role-window grants a ROLE; a workflow delegation records one PERSON
  exercising another's authority), which master-plan §1.1 #1's on-behalf-of mandate
  outranks. See `foundation.md` §7.
- **R-5**: template auto-assembly generates **print-faithful GAM Vol II forms**:
  App 32 DV support, App 44 Liquidation Report, App 45 Itinerary of Travel,
  App 46 RER, App 47 Certificate of Travel Completed.
  **R-5-gen shipped 2026-08-04 (session 19)** — core-services **#8** and **#3**
  (snapshot half) plus the reimbursement consumer: **App 45 Itinerary, AR-01
  accomplishment report and App 32 DV**, which are exactly the three
  `evidence='generated_doc'` catalog rows. The other two forms in this bullet
  are **not** R-5 work on inspection: **App 46 RER** is seeded as an `upload`
  (the traveller's own receipt) and **App 47 CTC** as `external_wet_sign` (a
  hand-signed page), so generating either would assert something the system
  cannot know; **App 44 Liquidation Report** belongs to the R-6 liquidation
  clock. Generation is **draft pre-submit** (watermarked, no reference number)
  and **regenerated authoritatively at submit** once `RB-YYYY-NNNN` exists,
  superseding the draft. `reimb_template_maps` landed here as a *binding* table
  (catalog code → registered document key), not the spec's placeholder-merge
  map — under Jinja the template IS the field mapping. **R-5-packet** still owes
  the combined printable packet and the §9.2 approver preview.
- **R-6…R-9** per spec: liquidation + settlement (refund OR capture / spawned
  reimbursement-due), external FMS tracking + pipeline board, insights/learning
  loop ("promote to pre-check"), hardening + pilot flag. Work-management
  non-negotiables throughout (one holder, one next action, My Work, holder-only SLA
  ladder, stalls visible, returns never orphan).

### Stage D — Landing shell, query bar, Calendar surface, AI (Phase 3)

Minimalist landing + deterministic intent matcher on NAV_GROUPS (incl. report
intents); **Calendar of Activities screen** — the connected calendar the owner asked
for: reads `core_activities`, travel claims, statutory deadlines (from
`core_compliance_deadlines`), and — as later stages ship — room bookings, document
deadlines, SPMS dates; shows cash-advance liquidation countdowns on funded events.
CSS-IS reverse-proxied into the shell (session carries). `ai_core` promoted to the
shared AI service (budget + `ai_interaction` reconciled with the query log).

### Stage E — Document Tracking & Workflow IS (Phases 4–7, renamed)

The reference §19 scope (logging ≤30 s, list/detail, parallel routing, staff queue,
two-dimensional status + derived Overdue, sub-tasks/consolidation, frozen-snapshot
signatures, Google Docs integration, rule engine + feedback loop, FTS, dashboards,
11 admin areas, archive) — built **on** the core engine, attachments, contacts, and
document-type taxonomy. Research corrections: **FOI clock = 15 working days + one
≤20-WD extension with pre-lapse written notice; deemed denial on lapse; appeal 15
calendar days → decision 30 WD** (the reference's "3/15/30" is wrong — the 3-day
figure belongs to RA 11032's separate 3/7/20-WD transaction tiers, modeled as their
own SLA dimension). Adds: **8888 hotline referrals** as a document type with a
72-hour clock (EO 6 s.2016); NAP records layer (incoming/outgoing registries with
per-year control numbers, record-series links to the **GRDS series of 2023**, NAP
Forms 1/2/3 generation, disposal gated on uploaded NAP written authority); quarterly
FOI Registry export (FOI-PMO template, identity masking) + annual summary; the DPO
backfill task that hardens reimbursement's `dpo_document_id`. DTrak manual + Google
Sheets sync stay at Stage I. Documents-only pilot at exit.

### Stage F — QMS module (`qms_`, new)

- **Controlled Document Management** (owner feature; ISO 9001 §7.5 + EO 605/GQMC
  conventions): 4-level hierarchy (QM → procedures → WIs/SOPs → forms), configurable
  document codes (`<OFFICE>-<TYPE>-<UNIT>-<SEQ>`), Rev. n + effectivity dates
  (approved ≠ effective; Celery flips Approved→Effective and current→Superseded
  atomically; exactly one effective revision per document), **DCR-only mutations**
  (creation/revision/obsolescence; originator → process owner → QMR → approver →
  document controller), MASTER/CONTROLLED/UNCONTROLLED discipline — every ad-hoc
  download watermarked "UNCONTROLLED WHEN PRINTED/DOWNLOADED" + downloader +
  timestamp; controlled-copy issuance with copy numbers + retrieval tasks;
  **view/download as separate permissions, default deny, every download logged**
  (the owner's download-permission requirement); live Master Lists (internal +
  external documents); external-issuance register (DOH AO/DO/DM/DC, COA/CSC/DBM
  circulars, YYYY-NNNN validation, superseded-by chains) — this backs the owner's
  "issuances/guidelines/memos" repository; obsolete stamping + restricted access;
  periodic-review clocks; documents vs **records** modeled as distinct lifecycles.
- **Risk & Opportunity Registry** (ISO §6.1, ISO 31000, NGICS): versioned criteria
  matrices (3×3/4×4/5×5 per tenant), server-computed scores banded to treatment
  rules (top bands require action + owner + target date), residual re-scoring,
  review cadence engine, ICQ/controls export for internal audit.
- **Management Review** (ISO §9.3 — the bureau's "MRR", confirmed default): input
  pack **auto-assembled cross-module** (all 9.3.2 items: CSM scores, audit results,
  KPIs, NC trends, risk-action effectiveness, resource flags, prior matrix of
  agreements), frozen as an immutable snapshot when conducted; outputs typed to
  9.3.3; matrix of agreements carries into the next cycle; block "conducted" until
  every input is populated or explicitly N/A-with-reason.
- **NC/CAPA register + internal-quality-audit program support** (§9.2: audit
  programme, plans/checklists, findings → NC linkage) — mandatory MR feeds and the
  ISO/PBB evidence chain.

Placement rationale: MR needs CSM + DTWIS KPIs + reimbursement KPIs to exist;
controlled docs reuse attachments/signatures/workflow. Risk Registry + MR sit here
(not in Performance) because ISO instruments cohere as one module — flagged as a
confirmable decision in §4.

### Stage G — CSS-IS convergence (Phases 1+8)

SQLite→PostgreSQL migration (per-table-class naive-Manila→UTC conversion, SQLAlchemy
async rewrite of `storage.py`, audit re-chain, dual migration: dev snapshot now +
fresh export at cutover), React strangler over the **~171-route** surface (bilingual
public form kept — M-3 re-scoped), and the **ARTA CSM v2023 instrument as versioned
config**: CC1–CC3 with skip logic, verbatim SQD0–SQD8, N/A options, scoring =
(SA+A)/(responses excl. N/A)×100 with SQD0 reported separately, MC 2023-05 bands as
data; **internal-services CSM triggers platform-wide** (reimbursement, bookings,
document requests are Citizen's Charter internal services); CSMR Annex-B generator
(sections I–VI incl. prior-year action-plan carry-forward; deadline default
**Apr 30**, configurable); **Citizen's Charter service catalog** doubling as the CC
source of truth (services, requirements checklists, processing times, fees) with CC
handbook generation and Certificate of Compliance support.

### Stage H — Admin + Reports + Government Outputs (Phase 9)

Admin: room reservation (double-booking prevention, optional weekly recurrence, no
approver) + announcements — bookings feed the Calendar. Unified Reports: dashboards
per module + leadership view + drill-down; XLSX-first exports for DBM/COA matrix
annexes (Excel is what URS encoding needs; PDF second). **Government Outputs
screen**: one card per mandated output — legal basis, period, working-day-aware
deadline countdown (from `core_compliance_deadlines`), source coverage %, last
generated + lineage, Generate button. Outputs at this stage: CSMR, FOI registry,
DTrak/communications registry, ISO evidence pack, liquidation/claim packets,
Calendar of Activities (CY), **Transparency Seal posting pack** (quarterly BAR/FAR
render set + APP + annual report items per GAA General Provisions), **consolidated
Annual Report** assembly, OPCR/WFP outputs joining at Wave 2.

### Stage I — Hardening, SIT, pilot (Phase 10)

DTWIS legacy migration (2,062-doc workbook, cleaning UI, "Migrated—Legacy Data"
flag, excluded from KPI baselines), bidirectional Sheets sync until cutover,
remaining CSS-IS React, security + resilience suites, load test against the real
Windows Server spec, **SIT includes one test per §1.3 connection-matrix row**,
pilot gate (1-week parallel run, Director on phone 5 days, zero data loss, <30 s
logging) → bureau-wide. Training track peaks here (§3.3).

### Wave 2 — the annual-cycle modules (post-pilot, flag-gated, own R-0 gates)

**W2-A · Planning & Budget (`plan_`)** — WFP as a DOH Budget Execution Document
(3 parts: physical plan with quarterly targets, monthly obligation program, monthly
disbursement program; two-tier BLHSD→HPDPB consolidation via the annual DOH WFP
Manual; server-side tie-outs: lines sum to ceiling per PAP/allotment class,
cumulative disbursement ≤ obligation); BED 1–4 generation from the approved WFP
(zero re-encoding; per-year deadline overrides — DBM reissues the November date
annually); BAR 1 workflow (frozen BED-2 targets, actuals, computed variance,
**mandatory remarks on deviation**, prepare→certify(Planning)→approve chain); FAR
1/1-A/1-B/2/2-A/3/4/5/6 calendar per COA-DBM JC 2019-1; allotment
(GAARD/SARO)/obligation/disbursement event ledger so FAR columns are pure queries
and obligations can't exceed allotment; budget-prep lifecycle (National Budget
Call → BP forms → OSBPS); **PPMP/APP under RA 12009 + GPPB Res 03-2025 forms**
(12-column PPMP with market-scoping-checklist gate; lot-level rows; MM/YYYY
precision; by-administration items retained; indicative→final semantics flip;
APP with indicative/final/updated versions + computed diff → highlight/bold
exports; CSE split to the APP-CSE workbook → mPhilGEPS (~Aug 31), summary-only in
the main APP; Final APP end-January + Certificate of Posting; PMR semestral; 11
modes + 13 negotiated instances + thresholds (SVP ₱2 M, Direct Acquisition ₱200 k)
as effective-dated config; EPA flags with award-blocking guards; per-record
`procurement_regime` for RA 9184 transitional items); **GAD Plan & Budget + GAD-AR**
per PCW-DBM-NEDA JMC 2022-01 (≥5 % attribution, HGDG scores, GMMS calendar);
APCPI indicator-input accumulation (assessment suspended pending NGPA tool —
collect the inputs anyway).

**W2-B · Supply Management (`supply_`)** — GAM Vol II chain with exact appendices:
PR (60) → PO (61, conforme date, ≤5-WD COA transmittal tracking) → IAR (62,
inspection ≠ acceptance, partial deliveries, liquidated damages 1/10 of 1 %/day,
10 % rescission) → RIS (63) / ICS (59, <₱50 k semi-expendable) / PAR (71, ≥₱50 k
PPE) with 3-year renewal clocks; **dual-card discipline** (Stock/Property cards in
Supply vs SLC/PPELC in Accounting — separate record sets, reconciliation views);
perpetual inventory + server-side moving-average costing; RSMI (64) bridge to
Accounting; physical-count mode → RPCI/RPCSP (Jan 31 + Jul 31) + RPCPPE (Jan 31)
per COA 2020-006 (tagging, found-at-station, shortages); disposal pipeline
IIRUP (74)/WMR (65) → appraisal → COA 89-296 modes → COA witnessing → derecognition
only via approved document; PTR (76) as the only custody-transfer mechanism;
loss/RLSDDP with the **30-day PD 1445 §73 relief countdown**; PIF → GSIS + COA by
Apr 30 (COA 2018-002); fidelity-bond adequacy tracking; PhilGEPS posting-evidence
fields on PRs/POs; year-end reconciliation schedules for the Feb 14 FS submission;
months-of-stock indicator (~3-month excessive-inventory watch); ₱50 k threshold as
effective-dated config (COA 2022-004; journal logic checked against COA 2024-006).

**W2-C · Performance & Deliverables (`perf_`)** — SPMS per CSC MC 6 s.2012 + DOH DO
2019-0440/2023-0084: configurable cascade OPCR→DPCR→(SPCR)→IPCR (SPCR is a DOH
form for hospital sections — tier count configurable, BLHSD default 3-tier);
pixel-faithful **DOH-SPMS Forms 1–8**; 4-stage cycle with signature gates
(commitments signed **before** the period; assessment "discussed with" ratee; final
rating by head); Q/E/T/A rating engine with NULL-aware averaging, DOH percentage
tempo + 40/50/10 weights as effective-dated tenant config, all-or-nothing
exception, written justification on any 5 or 2; **MOV required — "no proof → not
rated"** (MOVs are attachments/links to platform records); office-rating ceiling
validation (avg of individual finals ≤ office rating) + Form 5 generation; DOH
SPMS calendar ladder + adverse-action clocks (US notice ≤30 d post-semester, Poor
preliminary ≤15 d after month 3, IDP required); PMT + PRAISE committees with
queues; appeals (10 cal days → PMT 30 d; office rating immutable after review
conference); accomplishment reports (Form 6 quarterly → feeds BAR 1); PBB
delivery-unit ranking export (AO 25 machinery); **COA audit-findings lifecycle**:
AOM responses, AAPSI within 60 days of AAR + status reporting, NS/ND/NC records
with 6-month appeal windows — feeding the Risk Registry and Management Review.

Dependencies: W2-C targets pull from W2-A WFP/BED lines; W2-B's PR-vs-APP guard is
soft until W2-A ships. Recommended order A→B→C; B and C are swappable by bureau
priority. **LGU Health Scorecard / LHS maturity levels** (BLHSD's own UHC program
systems): scope to be confirmed with the bureau — planned as calendar/activity
feeds, not modules, until then. **Leave/DTR/attendance** (CS Forms 6/48, CTO rules):
out of scope as a module, but the data contract (who holds leave data that the IPCR
90-day rule and the calendar need) is an open decision (§4).

---

## 3. Cross-cutting tracks

### 3.1 Compliance gates (run across all stages)

| Gate | When | Content |
|---|---|---|
| PIA per module | before real data enters ANY environment (incl. UAT) | NPC Advisory 2017-03; per-module re-run (reimb, DTWIS, CSS, QMS, W2); dev/staging use synthetic data only |
| NPC DPS registration | before production | NPC Circular 2022-04; annual renewal calendared; **any auto-decision feature (auto-checks, auto-routing, auto-approve) makes registration unconditional** — enabling one triggers a registration review |
| NPC 2023-06 security baseline | before production | encryption at rest (BitLocker minimum, pgcrypto for ID numbers), MFA, control framework, BCP, training |
| Breach readiness | before production | 72-hour notify + 5-day report (Advisory 2026-02: the clock never pauses); incident table, runbook, "what did account X touch between T1–T2" query pack |
| Records retention | before first settlement | GRDS 2023: 10-year retention from final settlement for DV-supporting records; `legal_hold` + `retention_starts_at`; **no auto-purge ever** — disposal-eligibility report → human NAP Form 3 process (RA 9470: unauthorized destruction is criminal); soft delete ≠ records disposition |
| Export controls | with first bulk export | RA 10173 §22: SPI off-site cap 1,000 records; elevated approval + watermark + audit-log every export |
| Audit usability | Stage B | COA Res. 2020-034: auditor read-only role, per-record timeline, printable chain-verification report, full-dossier export |
| Audit payload policy | Stage B (decision §4) | no SPI **values** in immutable hash-chained logs (they can never be redacted) — log IDs + field names, resolve at read |
| E-signature per artifact | Stage C onward | RA 8792 / PNPKI / COA 2021-006 — decide per form with the resident COA auditor; default: system PDF is the workflow artifact, printed + wet-ink copy remains the legal record |

### 3.2 Ops & quality

Staging/UAT as a second compose project; CI on the new remote (pytest, lint-imports,
alembic single-head guard, module-boundary boot tests); structured JSON logs with
request IDs + self-hosted error tracker; Celery operability (retry/backoff policy,
dead-letter queue, failed-jobs admin view, beat single-instance); secrets convention
(+ rotation runbook, DR-rebuild path); **production substrate = Hyper-V Ubuntu LTS VM
+ Docker Engine** — not Docker Desktop (paid subscription required for government
entities), not WSL2 (no production support), not native Windows services (Memurai
licensing, supervision fragility) — this corrects the earlier tech-stack sketch and
is recorded there; only 443 published via Caddy/nginx with an AD CS/GPO-distributed
internal cert; Docker log rotation configured explicitly; Uptime Kuma on a different
machine (health, disk, cert expiry); quarterly restore drills incl. `verify_chain()`;
audit-log growth plan for the 10-year horizon (partitioning / checkpointed
verification); versioned image tags + expand/contract migrations; runbooks in
`docs/operations/` (restore, bare-metal rebuild, disk-full, cert renewal,
stack-down), printed + off-box copies.

### 3.3 Training & rollout (Rollout Track, from ROLLOUT §6)

R0 internal → R1 pilot cohort → Rn drip per module. Per module go-live: pilot cohort
(one division), parallel-paper period with exit criteria, role-based quick guides
(claimant vs approver vs admin), named super-users per division, in-app help slot
(WCAG 3.2.6 consistent placement), support/feedback channel (the platform feedback
widget), management sponsorship milestone. **Paper-fallback procedure**: documented
degraded mode for brownouts/LAN outage (UPS assumptions, "system unavailable"
paper forms, back-entry rules with original timestamps — COA clocks don't pause),
online-only stance stated explicitly.

### 3.4 Consolidated statutory calendar (seed for `core_compliance_deadlines`)

| Deadline | Cadence | Basis |
|---|---|---|
| CSMR to ARTA | Apr 30 (operative; configurable) | MC 2022-05/2023-05, MC 2022-01 |
| FOI Registry + Agency Info Inventory | quarterly (+ annual summary) | FOI MC 1 & 5 s.2017 |
| BAR 1, FAR 1/1-A/1-B/(1-C)/2/2-A/5/6 | 30 days after each quarter | COA-DBM JC 2019-1 |
| FAR 4 (Monthly Disbursements) | 10th of following month | JC 2019-1 |
| FAR 3 (Aging DDO) | 30 days after year-end | JC 2019-1 |
| BED 1–4 | mid-November (per-year DBM CL override) | annual Circular Letter |
| Final APP (HoPE-approved, + Certificate of Posting) | end of January | RA 12009 IRR §7.7.5 |
| Updated APP | end-July / end-January | GPPB-TSO advisory |
| APP-CSE → mPhilGEPS | ~Aug 31 of prior year (per PS-DBM advisory) | DBM CL 2011-6 |
| PMR | end-July / end-January | IRR §42.1(k) |
| RPCI / RPCSP | Jan 31 + Jul 31 | GAM; COA 2020-006 |
| RPCPPE | Jan 31 | GAM App 73 |
| PIF → GSIS + COA | Apr 30 | COA 2018-002 / RA 656 |
| PO copies → COA | 5 working days from issuance | COA 2009-001 |
| Year-end FS + schedules → COA | Feb 14 | GAM Vol I |
| SPMS ladder (targets, ratings, Form 5, IDPs) | Jan/Jul date ladder | DOH DO 2019-0440 Annex A |
| GAD-AR (via GMMS) | January | PCW-DBM-NEDA JMC 2022-01 |
| NPC registration renewal | annual (30 d before expiry) | NPC Circular 2022-04 |
| ISO surveillance / recertification | annual | certification body / GQMC-PBB |
| Liquidation clocks | per cash advance (30 d from return) | COA 97-002 / EO 77 |
| PAR/ICS renewals | every 3 years per slip | GAM / COA 2022-004 |
| Transparency Seal postings | per item cadence (checklist) | GAA General Provisions |

All effective-dated and tenant-overridable; working-day math via the core holiday
calendar; surfaced as countdown cards on Government Outputs with amber/red states.

---

## 4. Open decisions register

| # | Decision | Default / recommendation | Gate |
|---|---|---|---|
| 1 | R-0 set: liquidation clock basis (calendar vs WD), signatory chains per kind, cert-C wet-sign capture, directory seed detail, DTE cluster/HUC seed list (reframed: 3-cluster + PSGC map) | per research defaults; confirm with FMS/COA | R-0 |
| 2 | Off-box backup destination; git remote host | remote = GitHub private or Gitea on non-prod hardware; backups = second machine + offline disk | Stage A |
| 3 | Attachment storage: Google Drive vs local volume | **RESOLVED (Stage A / Increment 3):** local content-addressed volume is the prod default; the Shared-Drive-verified Google Drive driver is built and kept for tenants that want it (`core/storage/`). Runtime choice via `STORAGE_DRIVER`. | ~~Stage A / deployment~~ ✅ |
| 4 | Audit payload policy for SPI values | log IDs + changed-field names only for SPI-bearing tables | Stage B |
| 5 | E-signature validity per artifact | wet-ink remains the record; system PDF = workflow artifact; revisit with COA auditor + PNPKI later | Stage C+ |
| 6 | "MRR" meaning | ISO 9001 §9.3 Management Review Report | confirm with bureau, Stage F |
| 7 | Reports prefix (`rpt_` vs core lineage only) | fold lineage into core; no `rpt_` tables until a real table need appears | Stage H |
| 8 | Wave-2 order | A → B → C (B/C swappable by bureau priority) | after Stage I |
| 9 | QMS regrouping (Risk Registry + MR in QMS module, not Performance) | keep in QMS (ISO instruments cohere) | plan review ✔ (adopted) |
| 10 | LGU Health Scorecard / LHS maturity scope | calendar/activity feeds only until bureau confirms | W2 planning |
| 11 | Leave/DTR data contract (feeds IPCR 90-day rule + calendar) | define contract when W2-C is scoped; module itself out of scope | W2-C R-0 |

## 5. Reference corrections ledger (research vs references)

Recorded here once; each consuming module doc carries the delta in its register.

| Reference says | Correction | Source digest |
|---|---|---|
| Per diem ₱2,200 metro/HUC, ₱1,800 other | EO 77 Annex A: 3 clusters by destination region — I ₱1,500 / II ₱1,800 / III ₱2,200; per-day by that day's destination; effective-dated config | round1/ph-travel-reimbursement-rules |
| (spec silent) | Host-provided lodging/meals strip 50 %/30 %; gov-vehicle suppresses fare; excess-claim path; affidavit-of-loss never substitutes lodging OR | same |
| "Appendix A/B" (FS-BD-01 internal labels) | GAM Vol II: App 32 DV, 44 LR, **45 IoT**, 46 RER, 47 CTC (pre-2015 numbering had 44 = IoT) | same |
| Checklist per COA 2012-001 | Updated by COA 2023-004 — catalog versions pin to circular revision | same |
| FOI "3/15/30 days" | 15 WD + one ≤20-WD extension (notice before lapse); appeal 15 **calendar** days → 30 WD decision; the "3" belongs to RA 11032's 3/7/20-WD tiers (separate regime) | round2/arta-csm-foi-nap-records |
| CSMR due last working day of January | Operative practice Apr 30 (ARTA MC 2022-01 + annual advisories); keep configurable | same |
| (pre-2022 sources) ₱15,000 threshold | ₱50,000 per unit since COA 2022-004; semi-expendable logic per COA 2024-006 | round2/supply-property-management-gam |
| RA 9184 PPMP/APP formats, "Shopping" | RA 12009 + GPPB Res 03-2025 forms mandatory since 21 Sep 2025; Direct Acquisition ₱200 k; SVP ₱2 M; transitional flag for 9184 items | round2/ppmp-app-procurement-ra12009 |
| "MFO/PAP" hierarchy | PREXC since FY 2018 (JC 2017-1): cost structure → OO → program → subprogram → activity | round2/uacs-prexc-coding-spine |
| Auth: min 8 chars, ≥1 letter + 1 number | NIST 800-63B-4: no composition rules; length 12+ + blocklist (deviation recorded) | round1/auth-rbac-onprem |
| Migration-on-boot (foundation Inc 2) | Explicit deploy-step migration for prod; boot-migration dev-only, env-gated | round1/onprem-windows-server-ops |
| Prod = native Windows services (PG service, Memurai, NSSM) | Hyper-V Ubuntu VM + Docker Engine; Docker Desktop unlicensed for gov entities; WSL2 unsupported for prod | same |
| CSS-IS "stores UTC reference time" | Stores naive local Manila (CSS-RECON) — per-table-class conversion + re-chain | references/CSS-IS_Current_Build_Reconciliation.md |

## 6. Governance of this plan

- PROGRESS.md's phase tracker mirrors §2 (stages ↔ old phase numbers); statuses live
  there, scope lives here.
- Each stage's detailed build plan lives in its module doc (`docs/modules/…`); this
  plan holds sequence, connections, and cross-cutting obligations.
- Changes to this plan follow the session rules: update at session end, record the
  reason, commit locally.
