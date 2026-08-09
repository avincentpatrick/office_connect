# Office-Connect — Progress Tracker

## ▶ RESUME *(copy this one line to start the next session)*

> **Resume Office-Connect — Stage D Increment 3: CSS-IS reverse-proxied into the shell.**

That one line is all you paste. Per the start-of-session ritual I read the
*Current Status* + *Next Session Prompt* below (and the cited module docs) to
expand it into the full task and confirm with you before starting.

## ▶ CURRENT STATUS *(overwrite each session)*

- **Phase:** **STAGE D IS OPEN — Increments 1 and 2 are COMPLETE.** Stage C
  remains complete and pushed at `0.3.0` / `stage-c-complete`. **D-3 (CSS-IS
  reverse proxy) is next, then D-4 (`ai_core`).** D-1 gave the platform a front
  door; **D-2 gave it the first surface that reads the connection spine.**
  `GET /api/v1/calendar` + the `/calendar` page answer *what is happening, and
  what is due?* over three sources — activities, travel, liquidation clocks.
  Head is **`0024`**. Version stays `0.3.0`; Stage D's gate is the next
  promotion AND the next push.
- **Last session:** #30 — 2026-08-09 — **Stage D Increment 2: the Calendar of
  Activities. D-2 CLOSED.** Docs first (rule 1): **api-standards §9k**,
  ui-standards §4 template note, **new `docs/modules/calendar.md`** (rule 8),
  landing.md §1/§5/§6e, master-plan §1.1 **core-service #17** + §1.3. Then code:
  `core/calendar/{sources,service,activities}.py`, `core/api/calendar.py` +
  `schemas/calendar.py`, `core/features.py`, `workdays.load_nonworking_labels`,
  `activity.calendar.read` in the rbac seeds, migration **0024**,
  `modules/reimbursement/calendar.py`, `main.py` registration, richer fixtures;
  FE `api/calendar.ts`, `CalendarPage`, `calendar-copy.ts`, nav row + census,
  route.
- **✅ THE #29 SUITE MYSTERY IS SOLVED, AND THE ANSWER WAS ACCUMULATION.** The
  owner authorised the destructive reset. `docker compose down -v` + a full
  re-bootstrap, and the suite came back **1012 passed, 0 failed** on the first
  run. Three runs at #29 had each failed a *different* set; nothing about the
  code changed. **Evidence gathered before the reset, worth keeping:**
  `core_users` had reached **30,493**, `core_audit_logs` **568,461** — and
  `core_compliance_deadlines` held **70 rows of which 48 were leaked
  `csmr_to_arta_<hash>` test rows** against 22 real seeds.
- **⚠ `seed_guard` CANNOT SEE THAT CLASS OF LEAK, and this is the finding to
  carry.** It snapshots the rows each dataset *declares* and diffs them before
  and after the run — so it catches a seeded row **modified** and not restored,
  which is exactly the job it was built for at #28. Rows **ADDED** under fresh
  natural keys are invisible to it. Forty-eight hash-suffixed rows in a seeded
  reference table are what that blind spot looks like. A `seed_guard` sibling
  that fails a run which *adds* rows to a seeded table is the obvious next
  hardening; it was **NOT built this session** (scope), and it is recorded here
  rather than left to be re-discovered.
- **⚠ THE RESET DESTROYED FIVE ACCOUNTS NO CODE COULD RECREATE — now fixed.**
  PROGRESS.md described the six-account smoke cohort in prose, but only
  `no-grants@doh.gov` was reproducible (added to `bootstrap` at #29, precisely
  because someone had hit this wall once already). The other five had been
  minted by hand in earlier sessions. They are now `_SMOKE_ORG_UNITS` /
  `_SMOKE_STAFF` / `_SMOKE_ACCOUNTS` + `_ensure_smoke_cohort()` in
  `ops/bootstrap.py`, created idempotently by `load-fixtures`. **A cohort
  described in a document is not a cohort** — the same lesson `_backdated`
  learned about docstrings that ask callers to clean up.
- **The architecture decision D-2 turned on.** `oversight_scope` +
  `OVERSIGHT_PERMS` live in `modules/reimbursement/services/queue.py`, and the
  import-linter contracts forbid **both** `core → modules` and `module ↔
  module`. There is no import that reaches the rule. So the calendar
  **inverts**: core owns a `CalendarSource` value type + `register_source()`;
  each module implements a source where its own scope rule is a local import;
  `main.py` registers them. Precedent already in the tree —
  `core/notifications/outbox.py::register_enqueuer`. **This is not a workaround
  for the contracts, it is the shape they were protecting:** a join written in
  core would have hard-coded one module's org-placement rule into the platform
  floor, and contributor number two would have had to match it or fork it. Room
  bookings, DTWIS deadlines and SPMS dates now arrive as one file and one line.
- **The twelve D-2 kickoff decisions (all user-confirmed)** are recorded in
  `docs/modules/calendar.md` §5. The four that shape the code most: **(2)**
  activities tenant-wide, travel bounded by `oversight_scope` ∪ your own;
  **(3)** an agenda LIST on the existing `ListPage`, not a month grid; **(9)**
  state the RULE, never a count of hidden rows; **(11)** the liquidation layer
  is **own advances only**.
- **⚠ TWO CORRECTIONS FOUND DURING DESIGN, both worth remembering.**
  **(a) `reimb_claims.liquidation_deadline` is a MIRROR** —
  `cash_advance.py::link_claim` says so verbatim (*"a MIRROR, written here
  only"*), with `reimb_cash_advances.deadline_date` the source of truth. Feeding
  both would have drawn **two countdown rows for one obligation on the same
  day**, a defect that looks exactly like working software. **(b) There is NO
  set-form scope rule for cash advances anywhere:** `GET /cash-advances` is
  single-claimant and `deps.can_read_cash_advance` is a per-ROW rule placing a
  person by `staff.section_id or staff.division_id` — a *different* rule from
  the claim's `WorkflowInstance.org_unit_id`. Building the set form would mean a
  second org-placement predicate that must agree with the first forever. Hence
  own-only. Cost to widen later: one service function, two census rows, three
  security tests.
- **⚠ THE CENSUS GAP — the most important thing in this increment.**
  `tests/test_reimb_authz_census.py` filters routes on the
  `/api/v1/reimbursement` prefix and `test_reimb_scope_security.py` asserts
  `len(oversight_paths) == 3`. The calendar's travel source is a **FOURTH
  consumer of `oversight_scope`** living outside that prefix, so **both stay
  green whatever the calendar does.** Closed by three deliverables:
  **`tests/test_calendar_sources.py`** (a SOURCE census — the third instance of
  the R-9 pattern after `AUTHZ_TABLE` and `NAV_CENSUS`), **two new
  attacker-shaped tests inside `test_reimb_scope_security.py`** (where the other
  chairs already live), and an **amended drift message** naming the new file.
  `register_source` **raises** on an empty `scope_rule`, so the omission is
  impossible at import time rather than merely discouraged.
- **`reimb_claims.activity_id` is populated for the first time.** It had been
  validated on PATCH since R-1 and was non-null on **0 of 838** claims, because
  the wizard's activity picker was cut for want of an activities endpoint
  (reimbursement.md, spec §9.3 step 1). All 10 demo claims now carry one. **The
  picker itself is now UNBLOCKED and deliberately not built** — recorded as a
  deferral, not an oversight.
- **The clock convention a calendar needs.** No `freezegun` in this repo, by
  design. `?start=&end=` **IS the seam `_backdated` was faking**: HTTP tests
  create rows in a **private year (`_ISOLATED_YEAR = 2029`)** and ask for that
  year's window, so absolute assertions are safe and nothing needs undoing.
  `urgency` is the one thing a window cannot isolate (it is relative to *today*)
  — asserted as a SHAPE over HTTP, pinned exactly by `deadline.py`'s own unit
  tests. Rejected: a `?today=` debug parameter — a client-controlled clock on a
  surface whose job is stating deadlines is the same mistake as client-side
  money.
- **Smoke accounts (dev DB only), all `BoardSmoke!2026x`, NOW REPRODUCIBLE via
  `bootstrap load-fixtures`:** `board-smoke@doh.gov` (GLOBAL `admin_officer`),
  `scoped-officer@doh.gov` (`admin_officer` scoped to **Smoke Office B**),
  `smoke-approver-a@doh.gov` (`approver` on **Smoke Division A1**),
  `board-traveller@doh.gov` (plain `staff`, staff `SMK-A-1` in A1),
  `smoke-b-traveller@doh.gov` (plain `staff`, `SMK-B-1` in B1 — the stranger),
  and `no-grants@doh.gov` — **the only account that holds NOTHING; never grant
  it a role.** The tree is deliberately separate from BLHSD, and the scoped
  officer is granted on the **office** while staff sit in the **division** below
  it, so smoke exercises `descendants_or_self` rather than an equality on one
  unit.
- **⚠ Note on privileged roles in tests:** `approver` / `admin_officer` /
  `system_admin` require MFA enrolment before their session leaves the pending
  state, so an HTTP test that logs one in gets `mfa_setup_required`. That is a
  property of those roles, not of any surface — drive `staff` over HTTP and
  assert the grants against `ROLE_GRANTS` directly.
- **Test-hygiene note (still true):** a full-suite run leaves
  `module.reimbursement` OFF in dev. Flip it back with
  `python -m office_connect.ops.bootstrap set-flag module.reimbursement --on`.
- **⚠ FE test note (still true):** run the backend and FE gates **in sequence,
  not in parallel** — one `DocumentsStepPage` test flaked at #28 under CPU
  contention.
- **Blockers / waiting on user:** none.
- **⚠ Open questions for the accountant / resident COA auditor (unchanged by
  D-2):** **amount tiers** for both chains still need DOH DO 2019-0225/-0225A —
  both chains stay untiered and gain tiers as an authored v2. **Wet-signature
  capture** is narrowed to one question: whether the signed page must be BOUND
  to the step as a frozen snapshot (core-service #3's unbuilt half) or whether
  filing it under `CRT-C` suffices. The A/B/C **shape**, the **CTC-47**
  question, the **payout shape** and the **retention terminals** are all CLOSED.
  **Worth confirming when convenient (not blocking):** whether DOH BLHSD's FMS
  quotes a DV number *and* an ADA reference as two separate facts — if so, the
  payout record grows a second column as an authored v2.

## ▶ NEXT SESSION PROMPT *(rule 3 — the full brief I expand the RESUME line into)*

```text
Context: Stage A + B + C are complete and PUSHED (0.3.0, tag `stage-c-complete`). STAGE D
IS OPEN with TWO of four increments closed. D-1 gave the platform a front door (`/` is a
minimalist landing + a deterministic query bar, no API calls of its own). D-2 gave it the
CALENDAR OF ACTIVITIES: `GET /api/v1/calendar` + the `/calendar` page, an agenda list over
THREE sources - `core_activities` (tenant-wide), travel claims (scoped by
`queue.oversight_scope` UNION your own), and your own cash-advance liquidation clocks.
Head is 0024. Version stays 0.3.0 - Stage D's gate is the next promotion AND the next push.

THE SUITE IS GREEN AND THE #29 MYSTERY IS CLOSED. The owner authorised
`docker compose down -v`; after a full re-bootstrap the suite ran 1012 passed / 0 failed,
then 1046 with D-2's tests. The moving failures were ACCUMULATION, not a code defect
(core_users had reached 30,493; core_audit_logs 568,461; core_compliance_deadlines held 48
leaked `csmr_to_arta_<hash>` test rows against 22 real seeds). Do NOT go hunting a leaked
`set_audit_context` - that hypothesis is closed.
⚠ BUT ONE THING IS RECORDED AND NOT BUILT: `seed_guard` catches a seeded row MODIFIED and
not restored; it CANNOT see rows ADDED under fresh natural keys, which is what those 48
rows were. A sibling guard that fails a run which ADDS rows to a seeded table is the
obvious next hardening. It is a candidate for this session if you want a cheap, high-value
start; it is not required by D-3.

Task: STAGE D INCREMENT 3 - CSS-IS REVERSE-PROXIED INTO THE SHELL ("session carries").
Master plan Stage D. Expect a KICKOFF conversation before code - this increment is mostly
DECISIONS, and several are security decisions:
(1) WHAT does "reverse-proxied into the shell" mean concretely - an iframe, a path-prefixed
    proxy route, or a link-out? Each has a different session story and a different CSP one.
(2) HOW does the session carry? CSS-IS is a SEPARATE system (its own auth). Sharing a
    cookie across origins, minting a token, or SSO are three very different blast radii.
    api-standards §9j's rule binds here: telling a client what it may do is not authorizing
    it, and nothing on a request path may accept an entitlement claim.
(3) Is CSS-IS in this repo at all, or an external deployment? CHECK BEFORE ASSUMING -
    `module.css_is` is a seeded feature flag (migration 0001) and `docs/modules/css-is.md`
    exists, but no CSS-IS code has been written. If it does not exist yet, D-3 may reduce to
    a flag-gated nav row plus the proxy plumbing, and that is a legitimate outcome to
    propose rather than a shortfall.
(4) The CSP question is real: the artifact/browser story for embedding a third-party app
    inside the shell needs deciding before any markup is written.

FREE FROM D-2 - do NOT rebuild any of it:
- **The CALENDAR SOURCE REGISTRY** (`core/calendar/sources.py`, master-plan §1.1 #17,
  api-standards §9k). Any module that wants rows on the calendar writes ONE file and ONE
  line in `main.py`. Core owns the protocol, the merge, the window and the day grouping.
  `register_source` REFUSES a source with an empty `scope_rule`.
- `core/features.py::feature_enabled` - the single reader of `core_feature_flags`, shared by
  `require_feature` and the calendar's source dispatcher.
- `core/workdays.load_nonworking_labels` - names a holiday instead of merely greying it.
- The `activity.calendar.read` permission. `activity.read` / `activity.manage` are RESERVED
  for a future activity-registry maintenance screen - do not repurpose the calendar's grant.
- The reproducible SMOKE COHORT: `bootstrap load-fixtures` now creates all six dev logins
  (`_ensure_smoke_cohort`), their org tree (SMOKE-A/A1, SMOKE-B/B1) and staff.

DEFERRED, RECORDED, AND NOW UNBLOCKED - each is its own decision, do not start silently:
- **Reimbursement's wizard activity picker.** It was cut from v1 for want of an activities
  endpoint (reimbursement.md, spec §9.3 step 1). That endpoint now exists. All 10 demo
  claims carry an `activity_id`; real ones still cannot.
- **Statutory deadlines as a 4th calendar source.** DEFERRED with reasons in calendar.md
  §5a: `core_compliance_deadlines` has NO due-date column - it stores `cadence` + `due_rule`
  JSONB with **15 distinct kinds**, several unexpandable without inputs no table supplies
  (`per_certification_body`, `before_expiry`, `working_days_from_event`). Its real consumer
  is Stage H's Government Outputs countdown cards. Building it is an OCCURRENCE ENGINE, not
  a query.
- A month grid (fill-trigger: a user asking to see a whole month at once) · an activity
  create/edit write path · a calendar strip on the landing (D-1's no-API-calls property is
  deliberate and test-pinned).

⚠ THE CENSUS LESSON D-2 LEARNED, because it will recur at D-3. `test_reimb_authz_census.py`
filters routes on the `/api/v1/reimbursement` PREFIX; `test_reimb_scope_security.py` asserts
`len(oversight_paths) == 3`. The calendar became a FOURTH consumer of `oversight_scope`
OUTSIDE that prefix, and both tests stayed green regardless of what it did. Any D-3 surface
that reads module data from a core route has the identical hole. `tests/test_calendar_sources.py`
is the pattern to copy.

TEST HYGIENE IS MECHANICAL: `tests/conftest.py::seed_guard`; `_backdated` owns its undo.
⚠ A CALENDAR-SHAPED SURFACE USES THE PRIVATE-YEAR CONVENTION: `_ISOLATED_YEAR = 2029` in
`tests/test_calendar_agenda.py`, plus `_holiday()` - an async context manager that takes its
row back, because `core_holidays` has a live-rows-only unique index and a leaked row makes
the SECOND run fail on a constraint. There is no freezegun; services take an injected
`now`/`today`. ⚠ Privileged roles (approver/admin_officer/system_admin) need MFA enrolment
before their session leaves `pending`, so drive `staff` over HTTP and assert grants against
`ROLE_GRANTS` directly. ⚠ `import.meta.env.DEV` is TRUE under vitest - use
`vi.stubEnv("DEV", false)` for the production shape.
LIVE SMOKE EARNS ITS PLACE (#25 found a duplicate-notification defect every unit test
passed; #28 a claim-enumeration oracle; #29 a landmark/field accessible-name collision;
#30 confirmed the flag-OFF source really is ABSENT rather than empty).
Smoke accounts (dev only, all BoardSmoke!2026x), created by `bootstrap load-fixtures`:
board-smoke@doh.gov (global admin_officer), scoped-officer@doh.gov (scoped to SMOKE-B),
smoke-approver-a@doh.gov (approver on SMOKE-A1), board-traveller@doh.gov (staff, SMK-A-1),
smoke-b-traveller@doh.gov (staff, SMK-B-1 - the stranger), no-grants@doh.gov (holds NOTHING
- never grant it a role). Demo data: `bootstrap load-pilot-fixtures`.
OPS: after touching documents/, seeds.py or ops/, run `docker compose restart worker beat`
(tech-stack §5). The FE toolchain lives in the `web` container:
`docker compose exec web sh -c "cd /app && npm run typecheck && npm run lint && npm test"`.
RUN THE BACKEND AND FE GATES IN SEQUENCE, not concurrently. The backend suite takes ~12
minutes; expect to background it.
Read CLAUDE.md, then docs/master-plan.md Stage D + §1.1 (note NEW core-service #17) + §1.2 +
§1.3, docs/modules/css-is.md, docs/modules/calendar.md (all of it - §6b explains why the
liquidation layer reads the ADVANCE and not the claim's mirror column), landing.md §6e,
docs/standards/api-standards.md §9j + NEW §9k, ui-standards §3 + §4 (incl. the 2026-08-09
agenda note) + §6 + §7.
Rule 10 throughout; everything auditable + soft-deleted; money server-computed; no naive
datetimes; working-day math ONLY through core/workdays.
```

## Stage tracker *(rule 4 — commit per session, push per phase/stage gate)*

Stages per `docs/master-plan.md` §2 (old phase numbers kept for traceability).

| Stage | Old # | Scope | Status | Sessions | QA gate | Pushed (tag / date) |
|---|---|---|---|---|---|---|
| A | 0 (inc 1–4) | Foundation: spine ✅, ops ✅, integrations ✅, spine amendments ✅ | complete (pushed) | 1–6 | ✅ passed | `phase-0-complete` / 2026-07-23 |
| B | 2 | Identity & access: auth / RBAC / directory / delegation | complete (pushed) | 7–10 | ✅ passed | `phase-2-complete` / 2026-07-27 |
| C | R-0…R-9 | Reimbursement vertical + core workflow engine + first React shell | **complete (pushed)** — R-1…R-9 all ✅ | 11–28 | ✅ passed | `stage-c-complete` / 2026-08-05 |
| D | 3 | Landing shell / query bar / Calendar surface / AI service | **in progress** — D-1 ✅ (landing + query bar); D-2 ✅ (Calendar of Activities + the source registry); D-3 CSS-IS proxy next, then D-4 `ai_core` | 29–30 | — | — |
| E | 4–7 | DTWIS (Document Tracking & Workflow IS) | not started | — | — | — |
| F | new | QMS: controlled docs · risk registry · management review | not started | — | — | — |
| G | 1/8 | CSS-IS convergence (PG migration + React + ARTA v2023) | not started | — | — | — |
| H | 9 | Admin + Reports + Government Outputs | not started | — | — | — |
| I | 10 | Hardening / SIT / pilot gate | not started | — | — | — |
| W2-A | new | Planning & Budget (WFP/BED/BAR + PPMP/APP) | not started | — | — | — |
| W2-B | new | Supply Management | not started | — | — | — |
| W2-C | new | Performance & Deliverables (SPMS + COA findings) | not started | — | — | — |

Status values: `not started → in progress → QA → complete (pushed)`.
A stage's **Pushed** cell is filled only when its QA gate passed and the tag is
on the remote — that cell enforces the push-per-phase rule.
Governance gate (DOH / Data Privacy Act) blocks loading **real** data, not the
build; the PIA-per-module gate applies before real data in ANY environment
(master plan §3.1).

---

## Session log *(newest first)*

- **2026-08-09 (session 30 — Stage D Increment 2: the Calendar of Activities.
  D-2 CLOSED)** — the platform got its first surface that reads the connection
  spine. `core_activities` had a model, four FK holders and **no read path at
  all**; the column `reimb_claims.activity_id` had been validated on PATCH since
  R-1 and was non-null on **0 of 838** claims, because the wizard's picker was
  cut for want of an activities endpoint. D-2 built the endpoint.
  - **The suite question came first, and it is CLOSED.** #29 ended with three
    full runs each failing a *different* set, including at a commit D-1 never
    touched. The owner authorised the documented reset. `docker compose down -v`
    + a full re-bootstrap → **1012 passed, 0 failed** on the first run. The
    diagnosis was accumulation, and the numbers gathered beforehand are worth
    keeping: `core_users` **30,493**, `core_audit_logs` **568,461**, and
    `core_compliance_deadlines` holding **70 rows of which 48 were leaked
    `csmr_to_arta_<hash>` test rows** against 22 real seeds.
  - **⚠ The finding that outlives the reset: `seed_guard` cannot see that leak.**
    It snapshots the rows a dataset *declares* and diffs them, so it catches a
    seeded row **modified** and not restored — exactly the job it was built for
    at #28. Rows **added** under fresh natural keys are invisible to it. A
    sibling guard is recorded as the next hardening and deliberately **not built
    this session**.
  - **⚠ The reset destroyed five smoke accounts no code could recreate.**
    PROGRESS.md described the cohort in prose; only `no-grants@doh.gov` was
    reproducible, added at #29 because someone had already hit this wall once.
    Now `_SMOKE_ORG_UNITS` / `_SMOKE_STAFF` / `_SMOKE_ACCOUNTS` +
    `_ensure_smoke_cohort()` in `ops/bootstrap.py`, created idempotently by
    `load-fixtures`, with their own two-office tree (SMOKE-A/A1, SMOKE-B/B1).
    **A cohort described in a document is not a cohort.**
  - **The architecture, and why it is not a workaround.** `oversight_scope` lives
    in `modules/reimbursement/services/queue.py`; import-linter forbids `core →
    modules` **and** `module ↔ module`. No import reaches the rule. So core owns
    a `CalendarSource` value type + `register_source()`, each module implements a
    source where its own scope rule is a local import, and `main.py` registers
    them — the same inversion `core/notifications/outbox.py::register_enqueuer`
    already uses. A join written in core would have hard-coded one module's
    org-placement rule into the platform floor. Recorded as **api-standards §9k**
    and **master-plan §1.1 core-service #17**.
  - **Twelve owner-confirmed kickoff decisions**, in `docs/modules/calendar.md`
    §5 (a new module doc, rule 8). Load-bearing: activities tenant-wide and
    travel bounded by `oversight_scope` ∪ your own; an agenda **list** on the
    existing `ListPage`, not a month grid; **state the rule, never a count of
    hidden rows**; the liquidation layer is **own advances only**.
  - **Two corrections the design surfaced.** (a) `reimb_claims.liquidation_deadline`
    is a **MIRROR** of `reimb_cash_advances.deadline_date` —
    `cash_advance.link_claim` says so verbatim — so feeding both would have drawn
    **two countdown rows for one obligation on the same day**. (b) There is **no
    set-form scope rule for cash advances anywhere**: `can_read_cash_advance` is
    per-row and places a person by `staff.section_id or staff.division_id`, a
    *different* rule from the claim's `WorkflowInstance.org_unit_id`. Inventing
    one would be a security increment inside a read increment.
  - **⚠ The census gap, and the three things that close it.** The calendar's
    travel source is a **fourth consumer of `oversight_scope`** living outside
    the `/api/v1/reimbursement` prefix, so `test_reimb_authz_census.py` and the
    `oversight_paths == 3` assertion both stay green whatever it does. Closed by
    `tests/test_calendar_sources.py` (a SOURCE census — the third instance of the
    R-9 pattern), two attacker-shaped tests added to
    `test_reimb_scope_security.py`, and an amended drift message naming the new
    file. `register_source` **raises** on an empty `scope_rule`, making the
    omission impossible at import time.
  - **Statutory deadlines DEFERRED, with the reason on the record.**
    `core_compliance_deadlines` has no due-date column: it stores `cadence` +
    `due_rule` JSONB, and the live table carries **15 distinct rule kinds**,
    several unexpandable without inputs no table supplies. That is an occurrence
    engine, and its real consumer is Stage H's Government Outputs.
  - **The clock convention.** `?start=&end=` **is the seam `_backdated` was
    faking**: HTTP tests create rows in a private year (2029) and ask for that
    year's window. `_holiday()` is an async context manager that takes its row
    back — `core_holidays` has a live-rows-only unique index, so a leaked row
    makes the *second* run fail on a constraint, which is the same disease this
    session diagnosed. Rejected: a `?today=` debug parameter.
  - **Also landed:** `core/features.py::feature_enabled` (rule 10 — one reader of
    `core_feature_flags`, shared by `require_feature` and the source dispatcher),
    `workdays.load_nonworking_labels` (name a holiday, do not merely grey it),
    migration **0024** (`ix_reimb_claims_date_depart`), relative-dated demo
    activities spanning past/present/future with divisions, and all 10 demo
    claims linked to one.
  - **No new §3 component and no new §4 template.** `WorkItemRow` was
    deliberately left alone (its `to` is required; widening a contract for one
    consumer weakens it for six); the agenda row composes inventory pieces
    page-locally, per the R-5 `GeneratedDocCard` doctrine. The §4 note records
    the `<ol>`/`<h2>`/`<ul>` contract and forbids a `<table>` of days.
  - **QA:** backend **1046 passed / 0 failed** (10:32) on the finished tree,
    `lint-imports` **3/3**, `alembic check` clean at head **0024**; FE tsc +
    eslint + **353 vitest** (up from 325) + build. **Live smoke 27/27** over
    real HTTP as four actors, including the three properties only a running
    system shows: `no-grants@doh.gov` gets a **403** rather than an empty
    agenda; a **flag-OFF module is ABSENT from `sources[]`** rather than
    present-and-empty (flipped off, restarted, verified, flipped back); and one
    real draft trip is visible to its own traveller and invisible to the
    stranger while **both see the same activities**.
  - **⚠ `alembic check` earned its place this session.** Migration `0024`
    created `ix_reimb_claims_date_depart` but the ORM model did not declare it,
    so autogenerate wanted to DROP it — a migration and a model that disagree,
    which nothing else in the gate would have caught. Fixed by declaring the
    index on `ReimbClaim.__table_args__`.

- **2026-08-06 (session 29 — Stage D Increment 1: the landing shell + query bar.
  D-1 CLOSED; STAGE D OPEN)** — the platform got a front door. Before this,
  signing in dropped you onto a module page and `HomePage` was a 33-line
  placeholder. `/` now answers exactly one question — *what can this person
  open?* — and lets you get there by typing.
  - **The deferral this increment existed to lift.** `NAV_GROUPS` gated on ROLE
    CODES, because `/auth/me` never exposed permissions (ui-standards §7,
    recorded at R-2-shell: *"deferred until a surface needs finer gating"*). A
    landing page whose whole promise is "say plainly what you can do" is that
    surface. Two things were wrong, and the second had gone unnoticed for six
    sessions. **A grant-less user was shown a Reimbursement link that 403s on
    all 32 module routes** — and R-9 made that the *common* case, not the edge
    one, because nothing in this codebase auto-assigns a role, so the cohort IS
    the grant list. **And `me.roles` is a login-time snapshot:**
    `SessionStore.set_permissions_version` stamps the version onto live sessions
    but **never rewrites `roles`**, so a role granted after login did not change
    the nav until you signed out and back in — while api-standards §7 promises
    everywhere else that a grant lands on the **next request**. The old gate was
    not merely coarse; **it was out of date.** That is now an assertion, not a
    claim: `test_a_grant_lands_on_the_next_me_request_while_roles_stay_stale`
    proves the permission set is fresh **and** that `roles` is not, on the same
    request — which is precisely why `requiredRoles` was **deleted** rather than
    kept beside the new gate. Two gates, one stale, with no way for a reviewer
    to tell which is authoritative, is worse than either alone.
  - **One resolver, and the reason is the whole point.**
    `effective_permission_codes` was extracted so `/auth/me` and
    `require_permission` read the permission set through the *same* code path.
    Two readers of one set eventually disagree, and the visible form of that
    disagreement is a UI offering a destination the server refuses — §9f's
    failure mode arriving through the front door instead of a list endpoint.
    `test_the_me_surface_and_the_gate_agree` asserts the invariant directly: the
    payload claims `rbac.role.read` **and** `GET /rbac/roles` returns 200, or
    neither. Promoted to **api-standards §9j**, whose first rule is the one that
    would have cost the most: **a per-user payload never rides a shared-key
    cache** — `/api/v1/config` is Redis-cached under ONE global key and is
    already the endpoint the UI fetches at boot, so it is exactly where the next
    person will reach to put "one more thing the UI needs".
  - **`sorted()` is not tidiness.** `PermissionCache.get_or_load` returns a
    `set` on **both** the hit and the miss path. Emitting either directly makes
    the response non-deterministic **as a function of cache warmth** — stable on
    a warm dev box, arbitrary in production, and impossible to snapshot. Pinned
    by a test that calls `/auth/me` twice and asserts both are sorted and equal.
  - **The matcher cannot leak, structurally.** `nav-match.ts` is generic over
    `{label, intentKeywords}` and **imports nothing from `nav.ts`** — it has no
    way to acquire `NAV_GROUPS`, so it cannot offer a destination the caller did
    not already gate. §9f's mistake foreclosed rather than avoided by
    discipline. The test that pins it says so out loud: *finds nothing in an
    empty item list — it cannot see NAV_GROUPS.* Six tiers ranked
    exact → prefix → substring **interleaving label and keyword**, because a
    label and its keywords are two spellings of one destination rather than two
    levels of authority — so `"coa"` reaches Cash advances ahead of any
    incidental label prefix. Bucketed single pass, so declaration order survives
    inside a tier without relying on `Array.sort` stability. An empty query
    returns `[]`, not everything: returning everything would make the results
    indistinguishable from the idle page and the refusal indistinguishable from
    the idle state.
  - **The oversight gate is the server's rule verbatim.** Queue / board /
    insights now carry `OVERSIGHT_PERMS` itself rather than a three-role
    paraphrase, because holding any ONE of the three is exactly equivalent to
    `oversight_scope()` returning a non-empty scope. The backend test that pins
    the triple **names `web/src/app/nav.ts` in its failure message**, so moving
    the server's rule tells you which frontend file went stale.
  - **⚠ The query bar is a SEARCH FIELD, not an ARIA combobox** — the decision
    most likely to be "improved" later, so the prohibition is asserted rather
    than merely written down (`does not use combobox semantics` **is** the
    inventory row's contract). Radix ships no Combobox, so the pattern would
    mean hand-rolling `role="combobox"` + `aria-expanded` +
    `aria-activedescendant` + virtual focus: the hardest widget in ARIA, whose
    1.0→1.2 semantics changed incompatibly and whose announcements still differ
    across NVDA/JAWS/VoiceOver and are **unusable on iOS VoiceOver** — the
    platform ui-standards §6 puts first. What a combobox buys — an overlay popup
    and selection without moving focus — this surface does not need: the content
    under the bar *is* the list being filtered. Real links in a real list are in
    the tab order **by definition**, and are right-, middle- and Cmd-clickable
    besides. Enter is a deliberate no-op; Escape clears and keeps focus.
  - **Two findings the tests surfaced.** **(a) A landmark and its field must not
    share an accessible name.** The first `QueryBar` gave the `role="search"`
    form `aria-label={label}` — the same string as the visible `<label>` — which
    made `getByLabelText` ambiguous, and would make a screen reader's region
    list ambiguous with the control inside it. The landmark is now **unnamed by
    default**, with `landmarkLabel` opt-in for the day a page carries two search
    regions. **(b) `import.meta.env.DEV` is TRUE under vitest**, so the `devOnly`
    "UI foundation" item is openable in every FE test — which means the
    landing's **no-access state is unreachable in a dev build** while that route
    exists. Correct behaviour rather than a bug (in dev the item genuinely is
    openable; in prod it is statically eliminated), so the no-access tests assert
    the **production shape** via `vi.stubEnv("DEV", false)` while `nav.test.ts`
    asserts the dev shape *including* `/ui-foundation`. Neither test now passes
    for the wrong reason.
  - **⚠ The trap the design was built to avoid, and it is the likeliest bug in
    a page like this.** In the no-match state the natural implementation renders
    the openable list **twice** — once as "results", once as "everything you can
    open" — putting two nodes with the same `href` and the same accessible name
    in the DOM, which is ui-standards §4's *"one node, repositioned, never two
    copies"* violation. There is exactly **one** list on the landing; only its
    heading and contents vary, and a length-1 `getAllByRole` assertion guards it.
  - **The census ships from day one.** `nav.test.ts` carries a `NAV_CENSUS` on
    the R-9 census's reasoning: the risk is not a wrong row, it is a **missing**
    one — an item added tomorrow with no `requiredPermissions` is silently
    openable by everyone, and *absence never fails a test*. Unlike the backend
    census it needs no app introspection, because `NAV_GROUPS` is already an
    enumerable array. Every row must also name **the server rule it mirrors** —
    a cross-reference, not an assertion, since a browser test cannot check the
    server. This file proves the map is complete; the backend suite proves the
    territory matches it.
  - **⚠ `/auth/me` is no longer DB-free**, and the consequence is recorded
    rather than left to be discovered: under a DB outage *with* a cold cache it
    raises, `AuthProvider` yields `me = null`, `RequireAuth` redirects — so **a
    DB blip now reads as being signed out**. A distinct "we could not check your
    session" screen is a recorded deferral. It must never degrade to `[]`: that
    is the one option that lies, and it lies in exactly the no-access state this
    landing exists to tell the truth about.
  - **State (b) needed a new account to be testable at all.** All five existing
    smoke logins hold a role, and every seeded role carries at least
    `reimb.claim.read` — so the landing's no-access state, the common case after
    R-9, **could not be driven over real HTTP**. `no-grants@doh.gov` is created
    idempotently by `bootstrap load-fixtures`. It must never be granted a role
    "for convenience later": having none is its entire value.
  - **Docs first (rule 1), committed before any code.** ui-standards §3 row 24 +
    amendment block, a §4 **template note recording the decision NOT to amend**
    (a template exists to enforce mandatory loading/empty structure and this page
    fetches nothing, so there is nothing to enforce; one consumer is not a
    pattern), the §7 deferral lift, a §8 visual spec; **api-standards §9j**;
    `docs/modules/landing.md` §1/§5 and its previously-empty §6 filled with the
    four kickoff decisions, an 18-row delta register and the rule-10 check —
    **the query bar is NOT core-service #9 (Search)**, which is Postgres FTS over
    *records*; this matches labels on ≤7 nav destinations in the browser, and
    master-plan §1.3 says it in two words: *routing only*.

- **2026-08-05 (session 28 — Stage C R-9: hardening + the pilot gate. R-9 CLOSED
  and STAGE C CLOSED + PUSHED)** — a gate session, not a feature session. Eight
  increments had each been tested as they shipped; what had never been tested was
  the **set**, and spec §14's R-9 row carries its own exclamation mark —
  *"Security suite (scope filters!)"* — because that is where a hole hides.
  - **The suite found one on its first run.** `submit_claim` and
    `cancel_draft_claim` checked the claim's STATE before its OWNERSHIP, so a
    stranger POSTing `/claims/{id}/submit` against an id they did not own was
    told *"This claim is already in the approval workflow"*. Correct sentence,
    wrong audience. Set against `claim_not_in_workflow` for drafts and
    `reimb_claim_not_found` for ids never issued, it is a three-way
    **enumeration oracle** over every claim in the agency — filing volume and
    pipeline state, one probe at a time, from any ordinary `staff` login with no
    privilege at all. Every test in the repository passed, because every one of
    them submitted its own claim. **And the rule was already written down**, one
    file over: `services/drafts.py::owned_editable_claim` orders the checks
    correctly and names the hazard in a comment nobody in `lifecycle.py` read.
    Fixed in three places — the third being `claim_action`'s no-instance branch,
    which the workflow engine structurally cannot authorize (authorizing needs an
    instance; that branch is the one that says there isn't one) — and promoted
    from a comment to **api-standards §9i**: *authorization precedes state.*
    The corollary matters as much as the rule: do NOT collapse every refusal into
    `not_claim_owner`, because a scoped actor who is merely not the current step
    holder must still hear the engine's real answer, or an Admin Officer ends up
    reading that a claim they oversee is not theirs. Both halves pinned.
  - **The census is the part that outlives the session.** api-standards §9f's
    rule — *a list may not borrow a row's read rule* — had been applied four
    times, each time because a person remembered to. `test_reimb_authz_census.py`
    enumerates `app.routes` and requires every one of the **32** module routes to
    declare a gate class, a route permission and its exact service rule; a route
    added with no row **fails** rather than being missed. It reads the wiring off
    the running app through two new markers (`oc_permission`, `oc_feature_flag`)
    that core's dependency factories attach to what they return — a closure is
    otherwise opaque, and grepping the source would have re-created the
    hand-maintained-list problem the file exists to delete. Reading the finished
    table makes §9f's warning visible as data: **28 of 32 routes are gated on a
    permission an ordinary traveller holds globally**, so on almost every route
    the route gate provably is not, and cannot be, the scope rule.
  - **The pilot cohort is a stated posture, not a schema.** Before deciding,
    checked the thing the decision turned on: **nothing in this codebase
    auto-assigns a role.** There is no default-grant path, so a user reaches the
    module only because an administrator granted them one — the grant list
    already *is* the cohort, scoped, time-bounded and audited. Giving the flag an
    org dimension would have been a weaker second copy of RBAC plus a rewrite of
    the one endpoint the hard prohibitions say must never 500. What was missing
    was a way to *read* the cohort, so `bootstrap pilot-roster` reports every
    holder of any `reimb.*` permission with their scope and which are
    AGENCY-WIDE. The honest risk is written into §9i rather than left to be
    discovered: a cohort you cannot enumerate is a cohort you cannot verify.
  - **Test hygiene stopped being a matter of memory, after four recurrences.**
    #24–#27 each lost time to shared state left modified — a holiday row, aged
    `holder_since`, a promoted return reason — and each fix was a `finally` and a
    docstring asking the next person to remember. `seed_guard` now snapshots
    every seeded row's mutable columns and **fails the run** on unrestored drift
    (proven non-vacuous against a deliberately leaked promotion), and `_backdate`
    became a context manager that owns its own undo.
  - **Budgets are numbers now.** Both aggregates measured at ~5 ms. Migration
    `0023` adds the index the Insights window filters on — knowingly unused
    today, because the table is append-only and grows forever while its window
    stays fixed at 90 days. And `verify_chain` got the finding worth carrying:
    501,423 rows → 18.7 s but **1.47 GiB peak RSS**, so its ceiling is *memory*, at
    roughly 1M rows, and the failure mode is an OOM-killed integrity check —
    which reads as "the log cannot be verified" at exactly the moment somebody is
    asking whether it can be trusted.
  - **The gate.** Full suite green from an empty database, migrations replayed
    `0012`→head, seeds idempotent, FE gate green, live smoke 32/32 as three
    users. `[Unreleased]` promoted to `0.3.0`, `APP_VERSION` matched, tagged
    `stage-c-complete`, pushed. Stage C is done: a traveller can file a claim,
    have it approved, followed to FMS and paid; an advance can be liquidated and
    settled; and the module gets better as it is used.
  - **Docs:** api-standards **§9i**, database-standards **§7a**, module-doc
    **§4-M** (manual test guide — the QA gate required one and none existed),
    **§4a** (the spec §14 discharge table, clause by clause for R-1…R-9),
    **§4b** (perf budgets), five delta rows, the R-9 status row and the decisions
    log; development-workflow §4 (the stale "no remote exists yet" line corrected
    — it has existed since Phase 0 — plus the `stage-<letter>-complete` naming
    rule for stages with no old phase number); master-plan §1.1 (OCR re-deferred
    off R-9 to Stage H, since spec §14 never asked for it).

- **2026-08-06 (session 27 — Stage C R-8: insights + the return-reason learning
  loop. R-8 CLOSED)** — every return since R-4-screens has been required to
  carry ≥1 taxonomy reason, `reimb_return_events` has been filling up for four
  sessions, and **nothing had ever read a single row back**. This session is
  Objective 3: the first feature in the module that makes the system get
  *better* as it is used rather than only recording what happened. Spec §14
  grades it on two clauses — *"Promotion creates a working warning with no
  deploy; aggregates only"* — and most of the session went into making both
  literally true rather than approximately true.
  - **The `auto_checks` divergence is the decision the increment turns on.**
    Spec §11 says a promotion "writes an `auto_checks` row", and taken at its
    word that would have been wrong in the way that is hardest to catch: it
    would have worked. Our `auto_checks` are **item-scoped** — a check runs
    against one `reimb_checklist_catalogs` row, its flag sets that item to
    `auto_flagged`, and `engine.SATISFIED_STATUSES` counts `auto_flagged` as
    **DONE**. So promoting "Missing official receipt" through `auto_checks`
    would have marked a document *satisfied* and dropped a statistic into the
    approver's flag list. Two more blockers behind that one: no reason→catalog
    mapping exists, and reasons like `PER_DIEM_CALC` have no catalog row at all.
    What §11 is actually asking for is *"no code change"*, and one audited
    boolean on the reason honours it exactly.
  - **`promoted_check` was reinterpreted, not replaced.** The column has existed
    since R-1 (spec §5.6) and has never been read by anything, glossed loosely
    as "this reason CAN be promoted" with `True` on three seeded rows. Under the
    meaning §11 needs — *IS promoted* — those three are three warnings shown to
    every claimant that nobody authored. Migration **`0022`** resets them (a
    data-only migration, `down` restoring exactly those three codes), and the
    fail-safe argument is the one worth carrying: **on an advisory, "when in
    doubt" means do NOT warn**, which is the opposite direction from the packet
    gate and from every auto-check.
  - **The seed defect that would have undone the feature in silence.**
    `apply_dataset` writes only the keys a row dict lists. Leaving
    `promoted_check` in the seed would have made every `seed` run **demote every
    reason an Admin Officer had promoted** — on the next deployment, with no
    error, no audit row and nothing left behind but a warning that stopped
    appearing. The key is gone from all seven rows; the column keeps its
    `server_default` at insert and has exactly one writer thereafter.
    `test_reimbursement_seeds.py`'s assertion inverted to *nothing ships
    promoted*, which doubles as the canary for a leaked test promotion.
  - **The aggregate copies `column_totals`' shape, including its reasoning.**
    ONE grouped statement over BOTH windows (`count(*) FILTER`), because two
    round-trips would let a return landing between them be counted in neither —
    on a surface whose only job is counting, that is a wrong answer, not a
    rounding error. `reason_ids` is unnested with `jsonb_array_elements_text`
    and grouped **on the text element**: `queue._GRAND`'s `::numeric` is safe
    only because `compute.py` is the sole writer of what it casts, whereas
    `reason_ids` is FK-less JSONB with no database-level guarantee, so a SQL
    cast would 500 the whole surface over one bad element instead of logging it.
    Built on `queue.base_query(include_terminal=True)` so the *security*
    predicate has one definition in the module and not two that agree today.
  - **Privacy is structural here, not editorial.** Spec §11 is aggregates-only,
    mirroring §14.7's ids-not-values pattern. The ranking spans exactly the rows
    the actor could already open one at a time, which is why **no minimum-cell
    suppression was added**: in a small division the counts *are* about few
    people, and the actor already oversees precisely those people — suppression
    would protect nobody while making the numbers wrong. The response has no
    person dimension and nowhere to add one; the claimant's advisory carries the
    reason and never a count. Recorded as **api-standards §9h**.
  - **The write rule is narrower than the read rule — a first for this module.**
    Reading needs oversight of somebody; promoting warns *everybody*, so it
    requires an **agency-wide** `reimb.claim.review` grant. A division-scoped
    grant reaching a tenant-wide effect is a scope escalation that would look
    exactly like the button working. `can_promote` rides the envelope so the UI
    never offers a doomed control.
  - **Two true numbers, and neither is a rate.** A return citing three reasons
    is one packet that came back and three ranked citations; the header takes
    the first and says so. Spec §13's return *rate* needs a submissions
    denominator that stays in Stage H — and a plausible-looking percentage is
    precisely the number people quote.
  - **A reason that fell to zero keeps its row**, sorted last, labelled "down
    from N — none this period". It is what a successful promotion looks like, on
    the one surface built to show it; dropping it for having a zero count would
    delete the only evidence the loop works.
  - **`RankedBarList` earned an inventory row** (ui-standards §3.23) where the
    R-5 generated-doc card and the R-5-packet preview did not, and the line is
    worth remembering: **a bar ENCODES a quantity, and an encoding is what §3
    exists to standardize.** A `<table>` carries its own semantics; a bar
    carries none, so getting it wrong is an accessibility defect rather than an
    inconsistency. Built to the CountdownRing doctrine (bars `aria-hidden`,
    every number real text) plus two new rules: a bar is a share of the LARGEST
    ROW never of a total (a share of a total is a rate), and zero draws nothing.
  - **Test hygiene, THIRD shape — and this one is new.** Dates (#24) → counts
    (#26) → **shared seeded rows** (#27): a promotion is tenant-wide by design,
    so a test that promotes and forgets to demote leaves a warning standing for
    every later test and for the next developer's dev database. Every promoting
    test undoes itself in a `finally`. Separately, `reimb_return_events` REVOKEs
    UPDATE from `oc_app`, so a window/trend fixture physically cannot backdate a
    row — it INSERTs one with an explicit `created_at`, which is the append-only
    contract behaving exactly as designed.
  - **Verified:** pytest **907 (+17), 0 failures**; lint-imports 3/3; `0022`
    reversible down→up + `alembic check` clean; seeds ×2 no-op; FE gate green
    (tsc + eslint + **260 vitest**, +30, + build). **Live smoke 28/28**, and its
    centrepiece is a reconciliation rather than a shape check: six reasons and
    both windows against a raw `GROUP BY` over **535 real return events**,
    reason for reason — then spec §14's graded line driven end to end over real
    HTTP as two different users (promote → the claimant's taxonomy carries the
    warning, **no deploy, no restart, no migration** → demote → gone), with the
    441,731-row audit chain verified intact and the dev database left with zero
    promoted reasons.

- **2026-08-05 (session 26 — Stage C R-7-board: the pipeline board. R-7 CLOSED)**
  — R-7-queue made stuck work **findable** one row at a time, R-7-events made it
  **actionable**; this session answers the question a bureau chief asks from
  across the room, which is **how much is where**. Spec §9.6 calls the board
  "the module's public face" and spec §14 grades it on exactly one sentence —
  *"board totals match DB"* — so the counts and the peso totals are the product
  and the cards are context.
  - **The grouping lives ON the `Vocabulary`, per kind, and that is the one real
    design decision.** The columns are GROUPS of statuses (spec §9.2 says so out
    loud), so `board_column` sits beside `labels` where a state cannot be
    authored without one. The stakes differ from a label's, and that is the
    argument: an unlabelled state renders as a raw code at a user **who can see
    it is wrong**, whereas a state with no column disappears from a peso total
    with nothing on screen to say so. `None` is therefore an authored
    declaration — `draft` (nobody's oversight; My Work has it) and `cancelled`
    (spec §6.1 row 9, "excluded from KPIs" — 38 claims and ₱247,000 that never
    disbursed). `_assert_board_columns` runs at import and a test builds a
    deliberately broken vocabulary to prove it bites, because an assertion
    nothing exercises is a comment with a runtime cost.
  - **The trap nobody would find twice: the column sets must be PAIRWISE
    DISJOINT.** `column_totals` groups by status ACROSS both kinds in one
    statement and buckets the rows through the derived sets, so a code that one
    kind called In Bureau and another called Done would be counted in BOTH — and
    the board would total *more than the database holds*, which is precisely the
    sentence §14 grades. Asserted at import and pinned by its own test.
  - **`include_terminal=False`, not a second query builder.** Done is entirely
    terminal and `queue.base_query` excludes exactly that — its own R-7-queue
    docstring has said since session 24 that "R-7-board's columns are where Done
    gets counted". The flag won because `base_query` is the ONE definition of
    *which claims may this actor see*, and a second builder is a second copy of
    a **security predicate**: a drifted scope clause leaks, where a drifted
    display mapper merely renders wrong. The widening risk is a *default*
    problem, not a parameter problem. Explicitly rejected as too clever:
    "drop the terminal rule whenever `statuses` is given", which would silently
    turn `GET /claims?status=paid_closed` on the QUEUE into a list of paid
    claims. One test asserts both ends — in Done, absent from the queue.
  - **One grouped aggregate, `GROUP BY status`, not a SQL `CASE`.** The mapping
    then lives in one place instead of two, a dozen rows come back — and the
    real reason: **an unmapped status becomes observable.** A code left over
    from a retired definition version lands in no column and is LOGGED, where a
    `CASE` would silently `ELSE NULL` it. Which is also why the aggregate does
    not pre-filter on `ALL_BOARD_STATES`: that would hide the very rows the
    warning exists to catch. **Rejected: `core_workflow_instances.amount`** —
    already joined, already `numeric(12,2)`, no cast needed — because it is the
    engine's tier-routing guard input, not the module's money of record, and a
    board totalling the routing input would drift from the claim the day those
    two diverge. The `::numeric` cast on JSONB text is safe only because
    `compute.py` is the sole writer of `totals["grand"]` and goes through
    `money_str`; that is now a load-bearing invariant of another module and is
    named in the docstring.
  - **Done is bounded, the live columns are not** (user-confirmed at kickoff).
    `paid_closed` and `settled` accumulate forever, and an all-time figure stops
    saying anything about how the bureau is doing this quarter. 90 calendar days
    via `board.done_window_days`, fail-soft. In Bureau and With FMS stay
    unbounded on purpose — a claim stuck since March is exactly what spec §7
    rule 5 calls non-negotiable to show. The window's field is **`updated_at`**,
    because a terminal claim is read-only with no amendment route, so its
    `updated_at` IS the closing instant and it is the one field that means that
    on both kinds; `paid_on` is reimbursement-only and records when the *money*
    moved, which can precede the recording.
  - **`GET /board`, and the reason is a real trap** (user-confirmed at kickoff).
    `GET /claims/board` is the obvious URL and does not work: `claims.router` is
    included first, declares `GET /claims/{claim_id}`, FastAPI matches in
    registration order, and the path param has no convertor — so the request is
    read as a claim whose id is `"board"` and **422s**. Making it work means
    pinning `include_router` order, a dependency nothing declares and a future
    alphabetization silently breaks. A sibling segment is correct by
    construction. A test asserts BOTH halves so the reason outlives the
    decision. Now **api-standards §9g**.
  - **Done sorts differently, and it has to.** A terminal state CLEARS the
    holder, so `holder_since` is null on every Done row: "longest waiting" is
    not merely wrong there, it is *undefined* — every row would tie on NULL and
    fall through to `id`. Done sorts `updated_at DESC` (the same field the
    window filters on) and skips the urgency lift, because floating a finished
    claim over a more recently finished one answers a question nobody asked.
  - **The FE components were WIRED, not rebuilt** — and both needed a
    documented amendment first. `BoardColumn` had a `count` and no money slot
    and `BoardPage` had no skeleton or empty state, which ui-standards makes
    mandatory on every list and api-standards §9f calls a board. `PipelineCard`
    was explicitly "a board `<article>`, **no link affordance**" while spec §9.6
    says "clicking a card opens the tracker" — and standards outrank the
    reference spec, so the inventory was **amended rather than quietly
    contradicted**. The link goes on the TITLE under a stretched overlay: the
    whole card is clickable, and the accessible name stays "Regional
    immunization review" instead of ref + chip + title + meta read aloud in
    full, forty times down a column.
  - **`boardMeta` is a third meta composer, and the Done column is why.** Delta
    row 140's rule is one *row mapper* per row shape and it held — the board
    sends `QueueItemOut` unchanged, and `_queue_rows`/`_urgency_first` were
    extracted so three columns share ONE batched pass (one holiday window, one
    `DISTINCT ON`, one due-date query, not nine round-trips). What could not be
    reused was `queueMeta`: `days_in_state` is 0 on a terminal claim, so it
    would print **"0 days in this step" on a claim paid three weeks ago** — a
    false statement the queue never had to make, because a queue has no terminal
    rows. The shared `daysPhrase` was extracted so the working-days-with-FMS vs
    calendar-days-in-state distinction cannot fork.
  - **⚠ The full suite caught a THIRD instance of the session-#24 disease — in
    the file that documents it.** `test_reimb_api_queue.py`'s
    `test_stalled_claims_sort_above_longer_waiting_ones` and
    `test_a_global_grant_sees_every_office` both aged claims (365/730 and
    3650/3649 days) and never undid it, while `_backdate`'s own docstring says
    *"every caller must undo this in a `finally`"*. It leaked for three sessions
    and then failed: **54 permanently-aged rows had piled up**, the queue pages
    at 50 in longest-waiting-first order, so the freshly-aged claim fell off
    page 1 while the older one stayed — and the assertion was about a
    one-element list. The lift was working the whole time. Both are now wrapped,
    the 54 rows were reset, and the sort test additionally asserts **both**
    claims are on the page before comparing the order, because a one-element
    list trivially matches a prefix.
  - **The new hygiene rule this surface introduces:** on a COUNTED surface,
    absolute assertions are the same trap wearing a new coat — every other
    test's committed claims sit in these three columns, so `count == 3` is a
    claim about the whole suite. `test_reimb_api_board.py` asserts through a
    **scoped overseer** whose office `standard_cast` created fresh for that
    test, which makes every count and total about that test's claims and nothing
    else; the two tests that genuinely need a global grant assert membership
    only, never a number.
  - **The live smoke is what earns §14's line — 47/47 through the real stack on
    :8001.** Its centrepiece is a **reconciliation, not a shape check**: a raw
    `GROUP BY` over `reimb_claims` hand-bucketed through the three columns and
    compared to the endpoint, column for column and peso for peso
    (**In Bureau 1507 / ₱9,606,500 · With FMS 387 / ₱2,511,000 · Done 171 /
    ₱1,098,000**, with 39 cancelled claims and ₱253,500 shown sitting on no
    column). The behavioural half then drove a real `/mark-paid`: the claim left
    With FMS and led Done, both counts moved by one, both totals moved by the
    SAME ₱6,500, In Bureau was untouched, and **the board's grand total did not
    change** — which is the assertion that a move is a move and not a double
    count. Routing was pinned live too: `/board` 200, `/claims/board` **422**,
    and a plain traveller **403** whose message names My Work.
  - **Two things the smoke found that no unit test would have.** (1) Reconciling
    while the suite was still committing produced a one-claim divergence — not a
    defect but the READ COMMITTED skew, *observed* rather than merely reasoned
    about, and now recorded as accepted. **An aggregate surface must be
    reconciled against a QUIET database**, which is worth carrying into R-8.
    (2) The first claim the smoke picked off With FMS was a **liquidation**, and
    `/mark-paid` correctly refused it with R-7-events' chokepoint (*"a
    liquidation is settled against its cash advance rather than paid out"*) — an
    incidental confirmation that both kinds really do ride one board, arriving
    from the top of a live column rather than from a fixture.
  - **No migration** — everything the board needs already existed; head stays
    `0021`. Verified: pytest **890, 0 failures**, lint-imports 3/3, `alembic
    check` clean, seeds idempotent (161 unchanged, 0 written), FE gate green
    (tsc + eslint + **230 vitest** + build), live smoke **47/47**.

- **2026-08-05 (session 25 — Stage C R-7-events: the FMS journey record)** —
  R-7-queue made FMS-held claims **findable**; this session made them
  **actionable**, and closed three holes that were all live in the codebase at
  kickoff. `reimb_external_events` had shipped in migration `0013` with its
  index and its `REVOKE UPDATE` and had **never been written to** — grep found
  zero writers and zero readers, only two source comments promising "they ride
  `reimb_external_events` at R-7". `paid_closed` **recorded nothing**: spec §6.1
  row 8 calls it "terminal (admin records payout ref)" and it was a bare
  `approve`, so a claim closed holding no reference, no date and no way to add
  either. And every claim attachment in the system was **permanently
  non-disposable**, because `services/attachments.py` has parked
  `retention_starts_at=None` since R-2 waiting for a "R-7" that never came.
  - **The arrow in spec §6.1 row 6 is not a sequence, and that is the design.**
    The row reads *With Budget → With Accounting → Payment Processing (admin,
    **any order/skips allowed**)*, and the parenthetical is the operative half.
    FMS pays straight out of Budget, sends packets back to desks they already
    left, and answers "still with Accounting" twice in one week — every one of
    those is a legal relay. So `record_external_event` enforces MEMBERSHIP of
    the closed set and never ORDER; repeats are legal; and the 422 says *"in any
    order, and skipping any of them is fine"* **out loud**, because an operator
    who infers a sequence from a three-item list will not relay Accounting on a
    packet that skipped Budget. The FE mirrors it — no option is ever disabled
    by what came before. This is delta row 38 finally built: the sub-statuses
    are **not states**, they ride an append-only table over the single
    `handed_to_fms` state.
  - **"A relay moves nothing" is asserted, not assumed.** If a relay ever moved
    the claim it would also reset `holder_since`, and R-7-queue's ">10 working
    days with FMS" filter — the one surface that makes a stalled packet visible
    — would silently restart its clock every time somebody phoned FMS. The bug
    would have looked like diligence. A test pins status, holder, `holder_since`
    and the history row count across three relays.
  - **The relay works on BOTH claim kinds.** A liquidation sits at
    `handed_to_fms` too and is exactly as invisible while it does. Delta row
    116's liquidation exclusion is about `fms_returned` — a STATE, which would
    need a screen and a transition — not about a relay that adds no state and
    reuses one dialog. FMS runs both packets past the same three desks.
  - **`mark_paid` is workflow-standards §12's second instance, and the standard
    held without amendment.** `record_payout` writes the reference and the
    `paid` event, then drives the unchanged `approve`, all in one transaction;
    `_assert_payout_recorded` refuses the bare verb and NAMES `/mark-paid`;
    `claim_actions` rewrites the client verb rather than dropping it. Both
    chains now end in a rewritten verb, and the rewrite is **one kind-keyed
    table** rather than two `if` branches — two chains answering the same
    question in two places is how they drift on the day a third arrives. That is
    the only new advice the second instance produced, and it is now in §12.
  - **What FMS hands back was an open R-0-style question; the answer is
    deliberately small** (user-confirmed at kickoff): one reference plus a date.
    `payout_ref` / `paid_on` / `paid_by` in migration `0021`, **no unique
    index** — one LDDAP-ADA legitimately pays many disbursement vouchers — and
    `paid_on` a DATE rather than a timestamp, because when the money moved is
    the auditable fact and when somebody typed it in is already `updated_at`
    plus the history row. **The reference is REQUIRED**: `paid_closed` is
    read-only with no amendment route, so a blank one would recreate the very
    hole this closed, and the refusal names the honest alternative — relay
    *Payment processing* until the reference exists.
  - **The retention bug nobody could see, and rule 5 catching the first fix.**
    `retain_until()` had been returning `None` for every claim attachment ever
    stored, and the disposal report said "retention clock not started" — forever,
    and *correctly*, because it genuinely had not. `start_retention` went in
    CORE beside `retain_until` (rule 10, the `descendants_or_self` precedent):
    the module names the moment, core does the stamping, and both money
    terminals call it. The first cut was a bulk ORM `UPDATE` and
    `core/audit.py` **refused it at test time** — rightly, because starting a
    legal retention period is exactly the kind of change that must appear in the
    hash-chained log. Rewritten to load-and-mutate. `cancelled` deliberately
    does not stamp (user-confirmed): a voided claim produced no disbursement, so
    dating a disbursement-record retention period from its void would assert a
    disposal deadline for a payment that never happened. Recorded as a deferral,
    with a test pinning it so a later change is deliberate.
  - **One chronology, and the invariant the merge could have broken.** The
    tracker now merges `reimb_status_histories` with `reimb_external_events` —
    a claimant asking "where is my money" is asking ONE question, and answering
    it with two lists to interleave by hand is the tracker failing at its only
    job. `to_status` is **NULL on an external row**: a sub-status is not a
    workflow state, and letting `with_accounting` travel in the field every
    consumer reads as a claim status is how that distinction would quietly stop
    being true. The risk was the positional return-reason pairing (there is no
    FK; the k-th return row is the k-th return event) — so it is computed from
    the history rows ALONE, before the external lane is appended, and the merge
    is a sort at the very end. A regression test drives two returns with an FMS
    relay in the feed and checks the reasons landed on the right bounces.
  - **The live smoke earned its place again.** Every unit test passed and the
    28-check smoke still found a defect: `record_payout` writes a `paid`
    external event AND calls `notify_paid`, so a traveller got **two
    notifications about one payment** — the less informative one ("your claim is
    now Paid", no reference, no amount) arriving first. Both messages were
    individually correct, which is precisely why no assertion caught it. Now
    suppressed at the source and pinned by a test that asserts the whole outbox
    for the claim, not just the message it expects.
  - **A test-hygiene defect of exactly the session-#24 kind, one table over.**
    `test_reimb_api_queue.py::_backdate` aged COMMITTED claims to 21 days with
    FMS and never undid it. The suite shares one database, so every run left
    another permanently-over-threshold row until `?external_over=true`'s first
    page was nothing but old fixtures and the assertions stopped being about the
    claims they named. Fixed with `_undo_backdating` in a `finally` plus
    per-claimant scoping on the assertions. **The rule generalizes past
    holidays: any fixture that writes dates relative to TODAY must undo itself.**
  - **Six existing tests were updated, not worked around.** They closed claims
    with the bare `approve` this increment deliberately removes; each now drives
    `record_payout` and asserts the new contract, including that the bare verb
    409s and names the route.
  - **Verified:** pytest **860 (+38), 0 failures**; lint-imports 3/3; `0021`
    reversible (down→up→up) and `alembic check` clean; seeds ×2 no-op; FE gate
    green (tsc + eslint + **214 vitest**, +21, + build); **28/28 live smoke**
    through the real stack, plus a direct check that the GRDS clock really is
    stamped on the stored files and the outbox holds exactly one message per
    fact. Local commit only — push stays at the Stage C QA gate.

- **2026-08-04 (session 24 — Stage C R-7-queue: the oversight queue)** — R-7 is
  about the part of the journey that **isn't ours**: everything up to
  `handed_to_fms` is the platform's, and after that the job is to keep the claim
  findable, relay what FMS says, and record what FMS finally did. Spec §14's R-7
  row is four deliverables; **split three ways at kickoff (user-confirmed):
  R-7-queue → R-7-events → R-7-board**, with the queue first.
  - **The gap it closes, stated plainly.** `resolve_holder` sets
    `holder_kind='external_fms'`, `holder_id=NULL` at `handed_to_fms`, and
    `/my-work`'s "waiting on you" filters `holder_kind='user'` — so a claim with
    FMS appeared in **nobody's** inbox, and the Admin Officer who handed it over
    had no screen that ever showed it again. The holder modelling is correct
    (nobody in the bureau holds it) and the product was unusable. Every other
    R-7 button — the status relay, the `fms_returned` hand-back, `mark_paid` —
    hangs off a claim that could not be reached, which is why the queue is a
    prerequisite rather than the afterthought spec §14's ordering suggests.
  - **`GET /claims` — the module's first LIST endpoint, and the one security
    decision of the session.** Every read path before it asked "may this actor
    read THIS record"; a list asks it backwards. The naive translation is a
    hole: `reimb.claim.read` is granted **globally** to `staff` (a traveller must
    read their own claim from anywhere in the tree), so a list keyed on it hands
    every employee every colleague's destinations, purposes and peso totals. The
    queue is scoped on the OVERSIGHT permissions (`review`/`fms_update`/
    `approve`) and on the subtree those grants cover; holding none is a **403**,
    not an empty 200, because "there is no work" is a claim about the world and
    it would be false — and the refusal names My Work, the surface that does
    answer what that actor was asking. Written up as **api-standards §9f** so
    the next module's first list starts from it rather than rediscovering it.
  - **Core gained the missing half of its own scope primitive.**
    `ancestors_or_self` walks up from a record; a list needs the grants'
    downward closure, and doing it per row is a query per row unbounded by page
    size. `descendants_or_self` was built beside it in core (same recursive-CTE
    shape, soft-delete-stopped, depth-guarded) — rule 10: the module does not
    grow its own org-tree SQL.
  - **Spec §7 rule 5's ">10 working days with FMS", with no new column.** The
    count runs from `holder_since`, which for a claim sitting at
    `handed_to_fms` **is** the hand-off instant (nothing overwrites it while the
    state does not change) and which correctly restarts if a bounced claim is
    re-handed. Manila working days off the real holiday calendar, one window
    load per page. Deliberately *not* "days since the last external event": the
    rule asks how long FMS has HAD it, and a relay saying "still with Budget" is
    news, not progress. The threshold is config
    (`sla.external_followup_working_days`, default 10, fail-soft) because it is
    an operational knob, not a rule. `days_with_fms` is **null**, not 0, when
    FMS does not hold the claim — 0 would answer a question that does not apply.
  - **One row shape, one mapper.** `QueueItemOut` extends `WorkItemOut` rather
    than forking a second row type, and `work_item`/`holder_names` were promoted
    out of `api/my_work.py` into `api/deps.py` when the queue became their
    second caller. The queue adds exactly two fields, both of which My Work
    genuinely does not need.
  - **⚠ A test-hygiene defect caught only by its own flakiness.** The new
    holiday test seeds non-working days in the **recent past**, and the suite
    shares one database — so the rows silently shortened every later "working
    days since…" count in the codebase, including this file's own threshold
    test, which is how it surfaced. **Eight leftover rows were found and
    retired: Jul 27, 28, 29, 30, 31 and Aug 3 — an entire poisoned week.** The
    test now cleans up in a `finally`, retiring rather than deleting (rule 6).
    The general rule: **a fixture that writes dates relative to TODAY must undo
    itself.**
  - **Verified:** pytest **822 (+15), 0 failures**; lint-imports 3/3;
    `alembic check` clean (**no migration — head stays `0020`**); seeds ×2 a
    pure no-op; FE gate green (tsc + eslint + **193 vitest**, +7, + build); and a
    **23/23 live smoke** through the real stack — the claim absent from My Work
    and present in the queue, `days_with_fms` matching a hand-count off the
    holiday calendar, the stalled claim sorting to the top, a sibling office's
    claim invisible, and the traveller's 403 carrying
    `reimb_queue_not_permitted` rather than a borrowed "not the claimant".

- **2026-08-04 (session 23 — Stage C R-6-liq-settle: settlement)** — **R-6 is
  complete.** R-6-clock built the question, R-6-liq-chain built the chain, and
  this session built the answer's *content*. The measure of what was missing:
  `reimb_cash_advances.settled_at` had existed since migration `0013` and had
  **never once been written**, and `settled` was reached by a bare `approve`
  that recorded no money at all. Shipped as ONE increment — the seam that
  justified the five prior splits was absent, because GAM App 44's refund line
  prints the OR number that only settlement recording produces.
  - **The money and the terminal state are one act, on a concrete argument.**
    The engine's `approve` carries no payload, so the obvious shape was two
    calls — record, then approve. That was rejected because `mark_settled`
    releases the PD 1445 §89 slot the instant it commits: a settlement whose
    approve never followed would let the traveller take a NEW advance while a
    live liquidation still stood against the old one, and `0020`'s belt index
    then forbids repairing it. No compensating transaction exists anywhere in
    this codebase. Folded into one service call in one transaction, every
    failure rolls back together. `lifecycle.claim_action` gains the chokepoint
    that stops any other path asserting `settled` early, and the refusal NAMES
    the route that does the thing. Generalized into **workflow-standards §12**,
    because every future module with a money-carrying terminal step meets it.
  - **The client-facing verb is rewritten, not dropped.** R-4-screens' rule says
    never offer a button certain to fail; the naive reading here deletes
    `approve` and leaves a hole exactly where the approver needs a button. The
    actor IS authorized to clear that gate — they just have to carry the money
    while doing it — so `available_actions` offers `settle` instead. `spawn`
    joins on the same reasoning: the alternative was the browser comparing
    claimant ids, which is the client computing permissions.
  - **The brief was wrong, and grep was cheap.** `PROGRESS.md` asserted twice
    that `cash_advance.mark_settled` existed with no caller. It never existed.
    Written from scratch — and the one guard that mattered was *not* copying
    `mark_overdue`'s allow-list, which would have made an `overdue` advance
    unsettleable. Overdue advances are precisely the ones Accounting must close.
  - **The spawn is honest about the money, and that costs something.** Copying
    the trip, the itinerary AND the `cash_advance_id` is what makes DV-32 print
    the standard GAM shape — total claim, less cash advance, amount due the
    payee — with the difference on the payee line. Parking a bare difference in
    "other expenses" would have printed a fabricated expense category and an
    empty itinerary for a trip that demonstrably happened. The price is that
    `cash_advance_id` now means two things, so three readers were kind-guarded;
    one of them was a defect this increment CREATED (a settled-but-late advance
    would otherwise show a red Overdue ring and the COA interest/salary-deduction
    copy forever, on a record the traveller had already answered).
  - **What a generated form may assert about a certification.** `_dv32_body`'s
    rule survives intact and lands somewhere new: certification B's clearer is a
    fact the platform genuinely holds, so it is REPORTED in a note beneath a
    blank rule — never on the signature line, because a name over an empty rule
    reads as a completed certification to whoever holds the page. Certification
    C stays blank forever: the platform holds the Admin Officer who *recorded*
    the wet signature, not the accountant who gave it, and naming the recorder
    there would put the wrong person in a COA certification. There is now a test
    whose only job is to stop that being "helpfully" filled in. Written up as an
    **api-standards §9c corollary**.
  - **A pre-settlement Liquidation Report is honest, and the conditional is
    three-way.** A blank OR line *is* GAM App 44 at the stage it is at — the
    traveller walks it to the cashier and the number is written on. What would
    be dishonest is printing `₱0.00` (indistinguishable from "nothing
    refundable") or hiding the section so nobody learns money is owed. Settling
    reissues it, and the earlier copy is **superseded, not voided**: it was
    reissued, not invalidated.
  - **Three defects found in code this increment did not write.**
    `documents/service.py::_bindings` used `.in_([kind, None])` — SQL `IN` never
    matches NULL, so the "NULL = both kinds" semantic its own model documents was
    unreachable, silently, with a missing government form as the failure mode.
    `_dv32_body.html.j2` tested `{% if totals.advance %}` where `money_str(0)` is
    the truthy string `"0.00"`, so **every** reimbursement DV in the system
    printed `Less: cash advance (₱0.00)`. Plus the settled-advance countdown.
  - **The live smoke earned its keep on something no test can catch.** The suite
    was green at 807 and the smoke still failed twice: the Celery worker holds
    STALE Python while reading Jinja templates FRESH from the bind-mount, so it
    rendered new markup against an old context (`'money_labels' is undefined`)
    and could not resolve the newly registered `reimb.lr44` at all. A test
    process imports current code by construction, so this is structurally
    invisible to pytest. Recorded as an ops invariant in `tech-stack.md` §5:
    **restart the worker, not just the app.**
  - **Verified:** pytest **807 (+36), 0 failures**; lint-imports 3/3; `0020`
    reversible (down→up) + `alembic check` clean; seeds ×2 no-op; FE gate green
    (tsc + eslint + **186 vitest**, +9, + build); **25/25 live smoke** through
    the real stack — both money branches, the §89 slot release, the spawn's
    netting — plus a print-layer check that the reissued LR-44 carries the OR
    and its predecessor is `superseded`.

- **2026-08-04 (session 22 — Stage C R-6-liq-chain: the liquidation workflow)**
  — the module gains the *answer* to the clock R-6-clock built. **R-6-liq was
  SPLIT** (chain / settle) at kickoff — the fifth such split after R-2, R-4, R-5
  and R-6; the seam is chain-vs-money, and GAM App 44's entire content *is* the
  settlement figures. Four user-confirmed kickoff choices: **the split**,
  **certification A folded into submit**, **CTC-47 on both kinds**, and
  **liquidations reuse the 5-step wizard**.
  - **Generalized, not forked — and the fork was the tempting option.** A second
    `liquidation_status.py` plus a second lifecycle path would have shipped
    faster. But four state codes (`draft`/`returned`/`handed_to_fms`/`cancelled`)
    are genuinely SHARED and mean the same thing in both chains, so two copies
    would have duplicated them and drifted the first time one chain gained a
    state. Instead: one `Vocabulary` per kind, and
    `workflow._assert_graph_invariants` now takes the vocabulary as a PARAMETER —
    checking both graphs against one merged set would have accepted a liquidation
    state authored into the claim graph, the exact drift the check exists to
    catch. A test pins that a shared code never changes CATEGORY between kinds.
  - **The union-terminal trap, and why the fix is a derivation.** My-Work's two
    queries span both kinds in ONE statement, so they cannot resolve a per-row
    vocabulary — they filter on `ALL_TERMINAL_STATES`. Written by hand, that list
    would have omitted `settled` and left every finished liquidation sitting in
    its claimant's inbox forever. It is derived from the vocabularies and
    asserted *as* a derivation, so the next claim kind cannot reintroduce it.
  - **Certification A has no state, and the absence IS the decision.** Spec §6.2
    reads "Certifications (A→B→C in order)", but A certifies that the *claimant*
    incurred the expenses and the claimant is the MAKER. The engine's
    `enforce_segregation` guards `instance.originator_user_id`, so authoring A as
    a gate would have asked the maker to check themselves. Submitting IS
    certification A; the event log records who and when.
  - **The liquidation chain adds NO engine verb.** Its certifications are
    `approve` at gate states, exactly like the claim chain's approvals — so the
    un-gated `api/actions.py` drives it with zero new routes, zero new schemas
    and nothing new on the client beyond the labels. Rule 10 paying off in the
    direction it was supposed to: the second consumer of a shared engine cost
    less than the first.
  - **"Director IV" is a SCOPE, not a role.** `reimb.liquidation.certify` is a
    permission granted to `approver`; which person holds it at which org unit is
    grant data, and `resolve_holder` ranks nearest-first from there. A `director`
    role would have encoded a chain DOH DO 2019-0225 has not confirmed — the same
    deferral that keeps both chains' amount tiers unauthored.
  - **Certification C is a sentence, because that is all we honestly have.** The
    Head of the Accounting Unit is FMS and signs on paper. Its `approve` is the
    ONLY transition in either chain carrying `requires_comment`: the note naming
    whose signature and when is the entire record the platform holds. And
    **`CRT-C` is seeded `{"always": false}` for a structural reason** — the
    checklist gate is a PRE-workflow gate (it runs at submit and at every
    approve), so a required wet-sign row would have blocked submit and
    certification B, demanding the accountant's signature before the chain that
    obtains it had started. Delta row 67's argument, one level out.
  - **The first seeded `deadline_check`** lands on `LIQ-30` as `data_only`, so a
    late filing FLAGS without ever blocking — a late traveller must not be
    trapped unable to file the very liquidation that ends the lateness. Three
    sessions after the check was registered inert, it has substrate *and* a rule.
  - **NO migration — head stays `0019`.** The `reimb_claim_kind` enum already had
    `liquidation`, `status` is a varchar by decision (delta row 40),
    `cash_advance_id` already existed, and `allocate_reference_number` creates a
    `(scope, year)` counter on demand — so `LQ-` needed no seed either. `0020` is
    reserved for R-6-liq-settle's spawn link, the refund-OR columns and the
    one-live-liquidation DB belt.
  - **A real defect the gate caught and the tests did not:** `CashAdvancesPage`
    passed `<ErrorSummary items={…}>` where the prop is `errors`, so `errors`
    arrived `undefined` and `errors.length` threw — the record dialog would have
    **white-screened on any server error**, including the PD 1445 §89 409 that
    R-6-clock built its named message for. Every other call site already used
    `errors`. It survived R-6-clock because `tsc -b` is incremental and the stale
    build info never re-checked the file.
  - Verified: pytest **771 passed, 0 failures** (+34), lint-imports 3/3,
    `alembic check` clean with head still `0019`, seeds ×2 no-op (RBAC, reference
    and BOTH workflow definitions), FE gate green (tsc + eslint + **177 vitest**,
    +9, + build), and a **23/23 live smoke** through the real stack: an
    authenticated HTTP round-trip (record → Accounting refused → the traveller
    files → the second is a 409 naming the first → the advance names its
    liquidation), the LIQUIDATION catalog served instead of the claim one, the
    seeded `deadline_check` passing then flagging, and the whole chain walked
    `certify_b → certify_c → handed_to_fms → settled` with `LQ-2026-0002`.

- **2026-08-04 (session 21 — Stage C R-6-clock: cash advances + the COA 30-day
  liquidation clock)** — the module gains the other half of a travel claim's
  money story. **R-6 was SPLIT** (R-6-clock / R-6-liq) at kickoff — the briefed
  scope was roughly double any prior increment, the fourth such split after R-2,
  R-4 and R-5. Kickoff choices (user-confirmed): **calendar days with `basis` as
  a live switch**, **the split**, **Accounting records the advance**, and **fix
  both SLA-ladder problems here**.
  - **R-0 item 1 CLOSED — and closing it with a switch, not an answer, is the
    point.** COA 97-002 says "30 days" with no working-day qualifier, so the
    seed stays calendar; but the R-0 question was always whether DOH *practice*
    differs, which is a question about an agency rather than about arithmetic.
    `services/deadline.py` reads `basis` and routes to
    `core/workdays.py::add_working_days` when it says `working`, so a later
    confirmation is a config edit rather than a code change plus a data
    migration of every deadline in flight. Two lines of branch — and the guess
    would have mattered: the same "30 days" is **12 calendar days apart**
    between the bases (pinned by test).
  - **The deadline is PINNED, not derived** (migration `0019`:
    `deadline_date` + `deadline_basis`, backfilled). The practical reasons are
    the sweep's range query and the existing `liquidation_deadline` precedent;
    the decisive one is that a date a traveller was *told* must not silently
    move when an admin edits `liquidation.deadline` or a holiday lands in
    `core_holidays`. Recomputed on exactly one trigger — `date_return` moving —
    which is the R-5-gen `purpose` lesson (track which question an edit actually
    answers) applied to a clock. Re-dating also clears a stale `overdue`,
    because that verdict was about the OLD deadline.
  - **Compliance clocks fail SHORT.** An unreadable config row falls back to 30
    calendar days *and names the reason*; an unreadable *basis* keeps the
    configured day count, since discarding a legitimate `45` over a typo would
    be a second wrong answer on top of the first. This is the OPPOSITE direction
    to the checklist grammar's fail-OPEN for an unparseable rule — deliberately:
    a rule failing open leaves a **visible flag** a reviewer can action, while a
    deadline failing open quietly grants time that does not exist.
  - **PD 1445 §89 finally became a sentence.** The hard-block has been a partial
    unique index since R-1, which meant an Admin Officer who hit it got a raw
    `IntegrityError` → 500. It now names the blocking DV and its deadline, with
    the index still the actual guarantee and a pre-flight that races it
    deliberately — both paths raise the identical error, so losing the race is
    indistinguishable. §9.1 principle 4 applies to constraints too.
  - **The ladder warns at the level that is TRUE, not the level scheduled.**
    Milestones are "the most urgent threshold reached", so a beat missed to a
    worker restart still warns — and never sends "7 days left" on the day 3
    remain. The dedup key carries the **channel** (`…:<rung>:<channel>`) because
    D-3/D-0 send twice, in-app *and* email; without it the email spec §12
    promises would have silently deduped away against the in-app row. Overdue
    repeats stay in-app and carry their index. The class is `transactional`, so
    it bypasses opt-outs: a traveller may mute workflow chatter, never COA
    telling them their salary is about to be deducted. Deadline in calendar
    days, nudge cadence in working days — two different questions.
  - **`deadline_check` is live**, three sessions after R-3 registered it inert.
    `FACTS_VERSION` → **2**, because that is a change of MEANING for a key the
    catalog addresses by name. The seeded RULE deliberately waits for R-6-liq's
    catalog — a deadline check belongs on a liquidation — so what ships is the
    substrate plus a test proving `skipped → passed → flagged`.
  - **The 3-session-old test failure was the session-17 production defect.**
    `sweep_sla_reminders` budgeted `ORDER BY WorkflowStep.id ASC LIMIT 200` — a
    budget that always starts at the same end, so once ~200 steps are stuck,
    newly-overdue items are never nudged (spec §7.5 inverted). It surfaced at
    **session 18** only because that session added 146 tests and pushed the
    suite's accumulated backlog past 200; the dev DB held **450** such steps when
    measured. Fixed by most-overdue-first ordering **plus keyset-page draining**
    — ordering alone would not have fixed it, since the newest overdue item is
    by definition the *least* overdue and last in line under either ordering.
    Truncation is now logged. Two regression tests pin it, and the liquidation
    ladder was written drained from the start.
  - **Two findings, neither introduced here.** `created_by`/`updated_by` are
    **NULL platform-wide** (0 of ~1,450 live `reimb_claims`): the ownership
    columns exist on every business table and nothing populates them, so
    standing rule 5 rests entirely on the hash-chained `core_audit_logs` trail
    today. Recorded rather than widened into this increment — it touches every
    table. And **`FormDialog` now sets `noValidate`**: native constraint
    validation was BLOCKING the submit event on an empty required field, so
    react-hook-form never ran and the user got a browser bubble instead of the
    GOV.UK error ui-standards §3.14 requires to match the server's wording.
  - **UI:** **CountdownRing** promoted to inventory row 22 — unlike R-5's two
    page-local compositions it had three consumers on day one (My-Work, the
    register, the claim rail), which is exactly what "promote when a second
    appears" waits for. The ring is `aria-hidden` decoration and every fact it
    depicts is real text beside it; it displays a server value and derives
    nothing; "no deadline yet" is a state with words, because a full ring reads
    as plenty of time and an empty one as overdue. The status chip is dropped
    when it would only repeat the ring — R-5's "a second chip must earn itself"
    rule, applied.
  - **Verified:** pytest **737 passed, 0 failures** (+79), lint-imports 3/3,
    `0019` reversible + `alembic check` clean, seeds ×2 no-op, FE gate green
    (tsc + eslint + **168 vitest**, +18, + build), and a live smoke through the
    **real Celery worker**: pinned clock, §89 409, D-7 → D-3 → D-0 → overdue →
    repeat, idempotent re-beats, and an authenticated HTTP round-trip returning
    the server-derived countdown.

- **2026-08-04 (session 20 — Stage C R-5-packet: the printable packet + the §9.2
  approver preview)** — **completes R-5 and closes module-doc row 58.** An Admin
  Officer can now print one thing and walk it to Accounting. Kickoff choices
  (user-confirmed): **index, don't embed**; **same pass as the three forms**;
  **embedded frame from `lg` up, link at every width**. Decided and recorded
  rather than asked: the packet is a **claim-level artifact**.
  - **`reimb.packet` is registered but deliberately UNBOUND.** No COA circular
    names the folder its documents travel in — the circulars name the documents
    inside it. So the packet is generated *beside* the `reimb_template_maps`
    loop, calls neither `materialize_generated_item` nor `mark_generated`, and
    stores its join row with `checklist_item_id = NULL`. Because
    `claim_evidence()` and `evidence_counts()` already filter
    `checklist_item_id IS NOT NULL`, it is invisible to the Documents task list
    and uncountable as evidence with **no filter change anywhere** — the shape
    R-3 chose paid for this a session before it was needed. A test pins the
    asymmetry so nobody "fixes" it later by seeding a binding row.
  - **Composed by Jinja include, not by PDF merge.** Each form's body moved into
    a `_*_body.html.j2` partial that both its standalone template and
    `packet.html.j2` include, so **one** WeasyPrint pass yields cover → COA
    checklist → evidence manifest → the three forms in full. Live-verified at
    **6 pages**. Stitching three finished PDFs would have cost a `pypdf`
    dependency (rule 9) to reproduce markup we already had. Two generic print
    primitives went into core's stylesheet for it — `.page-break` and `.mono` —
    neither of which is knowledge about claims. The dynamic `{% include %}`
    resolves through a **code-side** `BODY_PARTIALS` dict, never through
    `reimb_template_maps.document_key`: deriving a template path from
    admin-editable data would hand the R-9 catalog editor a template-injection
    surface.
  - **The manifest indexes; it never embeds.** Each uploaded file is listed with
    its checklist code, filename, size, **SHA-256 of the original bytes**, scan
    state and custody. Three reasons, and the second is the load-bearing one:
    COA takes delivery of the **originals** (which is why
    `reimb_attachments.custody` exists), so a printed scan is not the evidence;
    and merging a claimant's PDF into a file that is served
    `Content-Disposition: inline` **precisely because we authored every byte of
    it** would break the entire §9c born-clean chain, taking the preview with
    it. A quarantined file is listed and marked, never silently dropped — a
    clerk counting envelopes needs to know a receipt was rejected.
  - **A document cannot carry the hash of its own bytes.** The cover prints the
    **`source_fingerprint`** instead: computed over the context, then injected
    into it for rendering only, with the new shared `comparable_context` nulling
    **both** `doc.generated_at` and `doc.fingerprint` before hashing. One helper
    for all four documents — two call sites computing "comparable" differently
    would make one of them look permanently stale. The cover also prints each
    embedded form's `content_sha256`, which is what ties a single loose page
    back to the packet it came from.
  - **Attach/detach became void triggers.** R-5-gen's invalidation was complete
    while the generated documents printed only claim data; the packet also
    prints a manifest of the uploads, so a file arriving or leaving dates it.
    Same argument that made `purpose` a trigger at R-5-gen, one level out.
    `services/checklist.py` calls `core.documents.void_snapshots` directly —
    `drafts → lifecycle → checklist` already exists, so importing `drafts` there
    would close the cycle. It voids only and never enqueues, or every upload
    would rebuild the whole packet mid-wizard.
  - **The generate endpoint grew a second door** (api-standards **§9d**, new):
    owner-while-editable, **or** a scoped `reimb.claim.review`/`approve` holder.
    Without it an Admin Officer whose next action literally reads *"Final check
    & print packet"*, and whose worker was down at submit, faces that
    instruction with no packet and no way to ask. Not widened to "anyone who may
    read it" — the `staff` read grant is global — and a refused bystander gets
    the owner path's error verbatim so the message is not an existence oracle.
  - **FE:** `PacketPreview` on `/claims/:id` (fourth section, above the sticky
    decision bar), on Review (marked **Draft copy**) and on the confirmation
    page. The frame is `lg`-only because **iOS Safari renders no PDF in an
    iframe** — an embedded-always frame would be a blank box on exactly the
    device §9.2 calls phone-first — so the new-tab link is the affordance at
    every width and only the frame is hidden. `test/a11y.ts` now runs axe with
    `iframes: false` (jsdom gives a frame no real window and axe throws trying
    to message it; the frame element's own rules still run).
  - **Docs:** api-standards **§9c corollary** (a generated document may contain
    only bytes we authored) + **§9d** NEW (two doors onto one endpoint);
    ui-standards §3 embedded-preview usage note (frame needs a `title`; frame
    enhances a link, never replaces it; absence is copy, not an empty frame);
    module doc **+6 delta rows** with **row 58 CLOSED**.
  - Verified: **pytest 658 (+9)** (1 pre-existing SLA-ladder failure, unchanged),
    lint-imports 3/3, `alembic check` clean with **no new migration** (head stays
    `0018`), FE gate green (tsc + eslint + **150 vitest**, +10), and a live smoke
    through the real Celery worker and real WeasyPrint: 6-page packet with every
    section present and the ref no. printed, `checklist_item_id NULL`,
    `origin=generated`/`scan=clean`, attach → 4 snapshots voided (reason kept,
    rows kept) → regenerate → the new receipt on the manifest.

- **2026-08-04 (session 19 — Stage C R-5-gen: template auto-assembly)** — shipped
  **core-service #8** and the **snapshot half of core-service #3**, and with them
  the module's Objective 1: a traveller enters trip facts once and the system
  writes the paperwork. Kickoff choices (user-confirmed): **WeasyPrint + Jinja2,
  Drive dropped entirely**; **draft pre-submit + authoritative regeneration at
  submit**; **snapshot half of #3 now, signature capture at R-6**; **R-5 split**
  into R-5-gen / R-5-packet.
  - **`office_connect/core/documents/`** — an ENGINE, not a form library. Consumers
    register a template directory and their own `DocumentSpec`s, so core renders a
    GAM appendix without ever learning what a claim is; `lint-imports` (3/3) is the
    proof, and it is the same inversion `core/attachments/authz.py` and
    `core/checklist/` already use. Jinja runs **autoescape-on + `StrictUndefined`**:
    the first stops a traveller's purpose text becoming markup in an official
    document, the second stops a missing key printing a blank amount on a voucher.
    The print stylesheet is built from `core/ui/tokens.py`, so standing rule 1
    (“tokens only”) reaches print and a tenant's brand colour changes its PDFs.
  - **The renderer is injected** (`renderer=None`, WeasyPrint lazy-imported inside
    it). That one choice is why the entire suite still runs on a Windows dev host
    with no Pango — tests pass a three-line fake — while production runs the real
    thing in the container, which is the only place the research digest allows it.
  - **Two hashes, deliberately.** `content_sha256` over the PDF bytes is tamper
    evidence; `source_fingerprint` over the canonical render context is change
    detection. PDF bytes embed a creation timestamp, so identical data renders to
    different bytes — hashing output could never answer “did the data move?”. The
    fingerprint is also what makes generation idempotent, so spec §10's “Celery
    task, idempotent, 3 retries” costs nothing on a retry.
  - **One new core column doing three jobs:** `core_attachments.origin`. Generated
    bytes are born `clean` (rendered in-process from autoescaped templates — and in
    prod `NullScanner` returns `error`, so leaving them `pending` would make every
    generated packet permanently undownloadable wherever ClamAV is absent); only
    generated PDFs are served `Content-Disposition: inline`, which is the only
    reason preview works at all; and the evidence tally filters them out so a
    system-produced artifact never counts as evidence a human supplied. Recorded as
    **api-standards §9c**, which knowingly amends §9b's “zero core router change” —
    how a blob is served is a property of the blob, and that is core's to know.
  - **`generated` had no writer.** R-3 shipped the status, but `_states` derives it
    from the very column `refresh_checklist` writes — a closed loop, which is
    exactly why the three items sat inert. `mark_generated` is the entry point, and
    `materialize_generated_item` is a deliberately SEPARATE door from
    `_item_for_catalog`: a claimant still cannot upload an IOT-45, and the generator
    still cannot manufacture a TO-01.
  - **A bug the unit tests could not have found.** The live smoke caught that packet
    invalidation was keyed on `_COMPUTE_INPUTS`, while `purpose` is printed on all
    three documents and moves no money — so editing it left an ACTIVE snapshot
    asserting a purpose the claim no longer had. `update_draft_fields` now asks two
    questions instead of one: did MONEY move, and did any PRINTED field move.
  - **`reimb_template_maps`** landed as a *binding* table (catalog code → registered
    document key), not the spec's placeholder-merge map: under Jinja the template IS
    the field mapping, and re-encoding it as JSONB would cost a second grammar to
    validate for no gain. Module doc row 31 CLOSED.
  - **Docs:** api-standards **§9c** NEW; tech-stack §2 (Jinja2 + weasyprint pins) and
    §3 (the Pango/libffi/fonts apt layer, with the never-on-Windows rule);
    ui-standards §3 usage note (why the Generated card is a composition, not a new
    inventory row, and why it carries ONE chip); module doc **+9 delta rows**;
    master-plan #8 and #3 marked SHIPPED.
  - Verified: **pytest 649 passed (+34) on a freshly migrated scratch database**
    (1 pre-existing SLA-ladder failure, proven not a regression by re-running the
    stashed baseline on a pristine DB — see Current Status), lint-imports 3/3,
    `0018` reversible + `alembic check` clean, FE gate green (tsc + eslint + **140
    vitest**, +3), **23/23 live smoke** through the real worker and real WeasyPrint.

- **2026-08-03 (session 18 — Stage C R-3: the checklist engine + uploads)** — built
  **core-service #7** and closed the two deferrals R-2-wizard and R-4-screens both
  pointed at. Kickoff choices (user-confirmed): **pure grammar in core** (not
  generic `core_checklist_*` tables), **hard 422 submit gate**, **waivers
  deferred**, **four computable auto-checks**.
  - **`office_connect/core/checklist/`** — pure, total, dependency-free.
    `grammar.py` implements exactly spec §5.3's operator set and nothing more
    (every operator in seeded JSONB is a forever contract); `checks.py` runs the
    six auto-check types, four over data that exists and two registered-but-inert
    with named reasons so a seeded rule can never silently pass; `engine.py` does
    the create/keep/restore/make_dormant reconciliation and owns the blocking
    rule. Dataclasses in, dataclasses out — `lint-imports` is the proof the seam
    is real.
  - **The structural decision:** blocking reads EVIDENCE STATE, never the `status`
    column. `status` is a derived read-model with one writer, exactly as
    `reimb_claims.status` mirrors the workflow engine. That single choice is why
    `auto_flagged` counts as done ("a flag never blocks alone", verbatim), why
    check results are re-derived on every read rather than stored (so the
    approver's callouts always describe the claim as it is NOW), and why R-3
    needed **no** check-results column and **no** `not_applicable` enum value.
  - **`generated_doc` never blocks** — a system-produced artifact cannot be a
    precondition of entering the workflow that produces it. Without this the three
    always-on `generated_doc` seed rows would have made every claim in the tenant
    permanently unsubmittable on day one.
  - **Uploads** ride core attachments end to end (Rule 10); the module keeps a thin
    join row and registers a `reimb_claim` holder authorizer, so core's download
    route became claim-scoped with **zero core router change** — collecting the
    promise `core/attachments/authz.py` made at Stage B.
  - **Two bugs fixed:** `reimb_attachments.retention_class` defaulted to
    `financial_10yr`, which is not a key of `RETENTION_CLASSES`, so `retain_until()`
    silently fail-safed to `None` — every claim attachment would have been
    permanently non-disposable and mislabeled in the disposal report (fixed in
    `0017` while the table still had zero rows); and `_cmp_eq` let Python's
    `True == 1` satisfy a boolean rule with an integer.
  - **FE:** the wizard's 5th **Documents** step (grouped GOV.UK task list, per-item
    upload, the §9.1 progress line, two chips per file because the ITEM being
    attached and the FILE being scanned are different facts), the Review gate
    (visible-but-disabled submit with an `aria-describedby`-linked panel and a
    deep link per blocker), and the approver's amber flag / red missing-document
    callouts. Inventory rows 20–21 (**FileUpload**, **Callout**) + the TaskList
    `action`/`detail`/`id` amendment — chosen over forking a second checklist
    component, because §3 says the task list "drives every checklist screen".
  - **Docs:** api-standards **§9b** NEW (a module owns the upload endpoint for its
    own entity); ui-standards §3 rows 20–21, the TaskList and Button amendments,
    and the dangling "§14" citations corrected to §3.14; module doc **+17 delta
    rows**, with row 45 and the §9.4 row CLOSED.
  - Verified: **pytest 616/616 (+146) on a freshly migrated scratch database**,
    lint-imports 3/3, `0017` reversible + `alembic check` clean, FE gate green
    (137 tests, +41), **19/19 live smoke**.

### Session 17 — 2026-08-03 — Stage C R-4-screens: the approver surface (completes R-4's UI half)

- **Phase(s):** C (R-4-screens — completes R-4 alongside sessions 11/15) ·
  **Commit:** `session(2026-08-03)` — **local only** (push at the Stage C gate).
- **Done:**
  - **The un-gated action surface** — `modules/reimbursement/api/actions.py`, a
    SECOND top-level router (`POST /claims/{id}/approve`, `POST /claims/{id}/return`)
    mounted from `main.py` **without** `require_feature`. It cannot be included under
    the gated router: FastAPI applies a router's `dependencies` to everything beneath
    it. The rule, now **api-standards §9a**: *the flag gates the module's surface; it
    never gates a decision on an instance already in the chain* (workflow-standards §9
    — `execute_action` never reads the flag). Reads + wizard writes stay gated;
    `/submit` needs no exemption (`start_instance` already refuses flag-OFF) and its
    resubmit branch stays gated (claimant-editing work). Pinned in
    `test_reimb_api_flag_gate.py`: flag OFF, the action routes must answer 401/403/409
    and must **never** return the gate's bare `not_found`.
  - **One `approve` for the whole chain** — the definition authors the same `approve`
    action on every forward move, so `division_approval → admin_review →
    handed_to_fms → paid_closed` needed one endpoint; only the LABEL varies by status
    ("Approve" / "Approve & hand to FMS" / "Mark paid & close"). A claim is now
    drivable to terminal over HTTP — the chain is e2e-testable for the first time.
  - **≥1-reason enforcement (closes delta row 44)** — `claim_action` rejects an empty
    `reason_ids` (422 `reimb_return_reason_required`) and any id outside the live+active
    catalog (422 `reimb_unknown_return_reason`), in the SERVICE not just the wire
    schema: `reason_ids` is FK-less JSONB and non-HTTP callers exist. Per-action routes
    (the kickoff choice) make the wire failure **field-anchored** (`loc:
    ["body","reason_ids"]`), so the FE mapper lands it on the chip picker itself.
  - **`services/actions.py`** — the per-actor action set (wrapping the engine, plus the
    pre-instance answer a draft needs: no instance exists before submit, so the module
    synthesizes the owner's `["submit","cancel"]`) and the spec §6.3 SLA badge
    (`on_track`/`due_soon`/`overdue`, server-derived). `ClaimDetail` now embeds
    `available_actions` + `row_version` (the CAS token) + `sla_due_at`/`sla_state`
    rather than serving a sibling endpoint — every mutation returns the whole claim,
    so buttons, token and record can never disagree.
  - **`api/tracking.py`** — `GET /claims/{id}/timeline` (append-only history merged with
    `reimb_return_events`; positional pairing, defensive on a count mismatch) and
    `GET /return-reasons`. **My-Work** rows carry `sla_due_at` + `sla_state` from one
    batched join over active steps — closes the delta row 52 deferral.
  - **Core fix (Rule 10)** — `available_actions` now mirrors `execute_action`'s two
    ACTOR-dependent gate guards (already-acted, and originator-under-segregation), so
    a chief who filed their own claim is no longer offered an Approve button that
    always 409s. Fixed in **core**, not the module — every future module inherits it;
    recorded as workflow-standards §3 doctrine (*an action listed is one the POST
    would accept now; a predictable 409 is a bug, a race-driven one is not*).
  - **Bug found + fixed en route** — an idempotent replay of a return appended a
    phantom SECOND `reimb_return_event` to an APPEND-ONLY hash-chained table (the
    module's insert sat after `execute_action`, which returns the original event
    verbatim on a key hit). Now guarded by a pre-check — which is also what makes the
    timeline's history↔return-event pairing exact.
  - **FE — the approval screen folded into `/claims/:id`** (one canonical URL for
    claimant, approver and bystander; what differs is entirely `available_actions`).
    New `ClaimActions` (server-driven bar: Approve behind a ConfirmDialog, Return
    behind the new FormDialog) and `ClaimTimeline` (first consumer of the
    built-but-unused `Timeline`, with return reasons as chips under their bounce).
    Inventory rows **18–19**: `ChipGroup` (a `<fieldset>` of real checkboxes styled as
    chips — chips are a look, not a widget) and `FormDialog` (a dialog whose submit is
    NOT wrapped in `Dialog.Close`, so failed validation keeps the user's work).
    `DetailPage` gains a sticky `actions` slot (§4 amendment) — **one** node
    repositioned by breakpoint, after the first draft rendered two copies behind
    `lg:hidden`/`hidden lg:block` and duplicated every id + announced every button
    twice. My-Work "Waiting on you" spends its one chip on urgency when a row slips.
    The wizard resume redirect now keys on `available_actions`, so a reviewer opening
    a returned claim is no longer dragged into a stranger's wizard.
- **Decisions this session:** kickoff (user-confirmed): **per-action routes** over a
  `{action}` envelope; **approval folds into `/claims/:id`**; **whole chain** with
  contextual labels; **new FormDialog + ChipGroup** over stretching ConfirmDialog.
  Design: un-gated = the two action POSTs ONLY (accepted residual: flag-OFF the
  approver *UI* is unreachable though the POST answers — the guarantee is that the
  engine and its HTTP mirror never refuse an in-flight transition, not that the SPA
  stays up); action set + CAS token embedded in `ClaimDetail`; **due-soon = 1 day**,
  because §6.3's 7-day window belongs to the R-6 liquidation clock, not a
  3-working-day approval SLA; **return comment stays mandatory** (engine
  `requires_comment` + spec §12's verbatim promise) though §9.2 calls it optional —
  recorded as a delta row; `/return-reasons` ordering comes free from the PG enum's
  declaration order (the catalog has no `sort` column).
- **Docs updated:** api-standards **§9a NEW** (+ §9 caveat resolved);
  workflow-standards §3 + §9 amended; ui-standards §3 (rows 18–19 + amendment note),
  §4 (template amendment + the app-wide z-index ladder), §8 (two visual specs);
  `docs/modules/reimbursement.md` (+9 delta rows, rows 44/46/52 closed, R-phase table,
  decisions log); master-plan R-2 + R-4 bullets; CHANGELOG `[Unreleased]`.
- **Verified:** **pytest 470/470 (+28)** — measured against a freshly migrated scratch
  database, because the shared dev DB now fails one *pre-existing* SLA-ladder test on
  accumulated residue (see the known issue above; the same suite is 469/470 there) —
  **lint-imports 3/3**, **`alembic check` clean** (no schema change — head stays
  `0016`), **FE gate green** (eslint + tsc + vitest **96** (+21) + build), and a
  **14/14 live smoke** on the dev stack:
  file → submit → return-with-reasons (0 reasons refused) → tracker shows the reasons
  verbatim → resubmit on the same RB- ref → approve → hand to FMS → mark paid & closed,
  plus the SLA badge, the draft action set, and the flag-OFF contract (reads 404,
  `/approve` answers 409 — never `not_found`).
- **Next:** **R-3 — the checklist engine + uploads** (core-service #7). It is the
  gate on spec §9.4's "never approve past a missing required item" and the wizard's
  missing 5th step, both explicitly deferred to it.

### Session 16 — 2026-07-30 — Stage C R-2-wizard: the claim wizard + My-Work inbox (the module's first HTTP surface)

- **Phase(s):** C (R-2-wizard — completes R-2 alongside sessions 13/14) ·
  **Commit:** `session(2026-07-30)` — **local only** (push at the Stage C gate).
- **Done:**
  - **The first module router** — `modules/reimbursement/api/` (schemas/deps/claims/
    my_work/reference), self-prefixed `/api/v1/reimbursement`, mounted from `main.py`
    (import-linter: core never imports modules), whole router behind the NEW core
    `require_feature("module.reimbursement")` dependency → flag OFF = 404 on every
    route, before auth (CSRF wall still outermost — all pinned by tests). Conventions
    recorded as **api-standards §9** (mounting, flag-404 + the action-endpoint caveat,
    read-scoping doctrine, deferrals: pagination envelope, Idempotency-Key header).
  - **9 endpoints**: POST /claims (draft birth via NEW `lifecycle.create_draft_claim`
    — status/holder/next-action stamped from the first row, §7 rule 1; server-side
    directory prefill: claimant block + `is_jo_cos` from employment status; prefill
    applied in the SAME tx via `drafts.update_draft_fields`); GET /claims/{id}
    (§3.2 owner-or-scoped: owner else `authorize_scoped` on approve/review/fms_update
    — the staff role's GLOBAL read grant can't scope, proven by the authz-matrix
    test); PATCH (whitelisted business fields; editing a compute INPUT clears
    `totals` so the FE task list re-opens Money); PUT /legs (bulk replace: server
    seq, soft-deleted removals, computed columns nulled); POST /compute (no body —
    returns the recomputed ClaimDetail; client never does money math); POST /submit
    (= `submit_claim`; `returned` claims route to resubmit — one FE flow covers
    fix-and-resubmit); POST /cancel; GET /my-work (holder-keyed "waiting on you"
    oldest-first + claimant-keyed "in flight", NULL-safe filters, batched holder
    names, cap 100); GET /regions (latest-effective PSGC→cluster rows).
  - **`other_total` column** (migration `0016`, snapshots backfilled from
    `totals->>'other'`): `compute_claim_totals(other_total=None)` now reads the
    column (explicit param persists first) — **fixes the latent
    resubmit-resets-other-to-zero bug** with zero call-site diff; `submit_claim`'s
    param removed. New `services/drafts.py` = the claimant business-field writer
    (owner + draft/returned guards; never touches status/holder). 5 new error
    factories. Bootstrap **`set-flag`** subcommand (audited UPDATE; dev flag now ON).
  - **The wizard (FE)** — 4 steps (Trip → Itinerary → Money → Review; Documents →
    R-3): react-hook-form 7.83.0 + zod 4.4.3 + resolvers 5.5.7 (exact-pinned,
    shape-only schemas), submit-per-step server-side save-and-return + task-list
    resume (state derived from field presence; `totals` presence gates Money),
    useFieldArray legs editor, Money = PATCH→/compute chained mutation with the
    running-totals rail (`WizardPage.asideExtra`), check-your-answers SummaryLists
    with ?from=review Change links, ConfirmationPanel with the RB- reference,
    read-only ClaimDetailView (+ in-place render for non-editable step routes — a
    post-submit redirect would race the confirmation navigation), unsaved-changes
    blocker (useBlocker + controlled ConfirmDialog + beforeunload), 422→RHF mapper
    (dots→dashes DOM-id convention), MutationCache 401 handler (me-exists guard).
  - **My-Work landing** replaces the placeholder: "Waiting on you" above "Your
    claims in flight" (WorkItemRow: ref+title link, StatusChip, holder · days ·
    next-action · ₱grand meta), per-section zero-states (🎉 aria-hidden), module
    EmptyState with Start-a-new-claim (button-triggered create — StrictMode-safe).
  - **Inventory 14 → 17** (ui-standards §3/§8 amended FIRST): Form-field family
    (SelectField/TextareaField/CheckboxField/RadioGroupField over internal
    FieldChrome; FormField widened to `ComponentPropsWithRef` for RHF register),
    SummaryList, ConfirmationPanel, WorkItemRow; Dialog controlled mode; WizardPage
    `asideExtra`; pages/<module>/ grouping convention (§7).
  - **Tests**: backend +27 (4 files: flag-gate ordering incl. CSRF-before-flag,
    draft CRUD + prefill + JO/COS + soft-delete legs + cancel history, §3.2 authz
    matrix, HTTP wizard walk hitting the ₱5,500 anchor + ONE ref burned + double-
    submit 409, resubmit-keeps-other regression, My-Work membership/ordering/leak/
    terminal tests, regions); FE 73 total (+45: component+axe for all new inventory,
    wizard-steps derivation matrix, form-errors mapper, claim-forms schemas, and the
    FIRST page-level tests — MyWorkPage/TripStepPage/ReviewStepPage on a new
    harness.tsx + stubbed fetch). `tests/conftest.py` promotes `CSRF` + `login`.
- **Decisions:** recorded in `docs/modules/reimbursement.md` §5 (2026-07-30 entry) +
  10 delta-register rows; api-standards §9 new; ui-standards + tech-stack §4 amended.
- **Adversarial review pass** (45-agent find→verify workflow over the diff): 13
  confirmed findings, ALL fixed pre-commit — headline: `submit_claim` never checked
  status, so a **cancelled draft could be resurrected and burn an RB number** (now
  guarded under the row lock + `reimb_claim_cancelled` 409, ditto double-cancel);
  drafts guards re-ordered owner-before-editability (killed a claim-status oracle
  for non-owners); RadioGroupField fieldset now carries the group id (ErrorSummary
  anchors were dead links); Money step writes the PATCH result to the cache before
  compute (no stale totals on compute failure); server field errors de-duplicated in
  summaries; confirmation deep-links for returned/cancelled claims corrected;
  attestation radios start unanswered on a fresh Trip step; + 4 coverage gaps closed
  (submit-after-cancel, resubmit-over-HTTP incl. the 0016 regression end-to-end,
  stale-totals both directions, confirmation deep-links). 7 findings refuted.
- **Verified:** pytest **442/442** (+29), lint-imports 3/3, `alembic check` clean at
  head **`0016`** (upgrade applied live), seeds ×2 no-op, **FE gate green** (eslint +
  tsc + vitest 75 + build), live e2e smoke through :5174 (config serves the flag ON,
  anonymous gated API → 401, SPA serves the module routes) — the wizard is walkable
  in a browser.
- **Next:** R-4-screens — the approver surface (see ▶ NEXT SESSION PROMPT; three
  open kickoff questions: action-endpoint shape, approval-screen route, FMS scope).

### Session 15 — 2026-07-29 — Stage C R-4-app: workflow definition + claim wiring + SLA delivery

- **Phase(s):** C (R-4-app — completes R-4 alongside session 11's engine core) ·
  **Commit:** `session(2026-07-29)` — **local only** (push at the Stage C gate).
- **Done:**
  - **The `reimbursement.claim` definition v1** (`modules/reimbursement/workflow.py::
    ensure_claim_definition`, idempotent on "a published version exists"; also bootstrap
    **`seed-workflows`**): spec §5.5 role chain on the §6.1 machine — draft →
    division_approval (gate, `reimb.claim.approve`, segregated) → admin_review (gate,
    NEW `reimb.claim.review`, segregated) → handed_to_fms (gate, NEW
    `reimb.claim.fms_update`) → paid_closed; return loops (comment mandatory, on the
    TRANSITIONS — engine reads current-state flags only), returned→resubmit (fresh
    revision) / cancel; **NO reject, NO amount guards** (deltas recorded). Originator
    transitions carry `reimb.claim.review` — a permission-less one is an engine open
    gate (verified). Seeder self-asserts: no permission-less gates, action subset,
    vocabulary coverage.
  - **`services/lifecycle.py`** — the single sanctioned mutation path
    (workflow-standards §1): `submit_claim` (claim-row `FOR UPDATE` → owner check →
    org unit from staff section/division fail-closed → `compute_claim_totals` →
    `start_instance` with flag gate BEFORE the `RB-` allocation (Manila year) →
    `execute_action(submit)` → sync + SLA stamp — one transaction); `claim_action`
    (approve/return/resubmit/cancel; default idempotency keys; resubmit recomputes
    totals + refreshes `instance.amount` pre-route; return also writes
    `reimb_return_events` with the returned step id recovered module-side);
    `cancel_draft_claim` (no instance pre-submit — same chokepoint). Sync writes
    status (= state code verbatim, `services/status.py`), holder trio, §6.1
    next-action copy + a history row ONLY on real moves (multi-slot partial approvals
    emit same-state events).
  - **Holder resolution** (spec §7.1, fail-closed): claimant states → owner user via
    `User.staff_id` (fallback originator); gates → NEW
    `core/org_units.py::permission_holders` (inverse of `authorize_scoped`;
    `ancestors_or_self` now proximity-ordered) — **scoped grants only** (global/
    system_admin never "the" holder), nearest unit → lowest id, originator excluded
    under segregation, zero match → 422 refusal (never a null holder);
    handed_to_fms → (`external_fms`, NULL); terminals cleared.
  - **SLA working-day stamping + delivery**: gates authored `sla_hours=None`; the
    wrapper stamps `sla_due_at` = Manila date + `add_working_days(config 3 WD)` @
    17:00 Manila → UTC (holidays honored; `handed_to_fms` never stamped);
    `services/notify.py` (pure) + `ops/reimbursement_tasks.py`:
    `register_sla_enqueuer` wired (defensive re-read — the seam fires pre-commit
    inside the sweep tx), beat `ops.reimb_sla_reminders` daily 08:30 Manila runs the
    repeating 2-WD **holder-only** ladder (outbox `dedup_key
    reimb.claim.sla:<step>:<k>` idempotency + `reminder` events). Superiors never
    notified.
  - **RBAC/bootstrap/schema**: catalog + grants + NEW `admin_officer` role
    (rbac.py); `load-reference` now applies module seeds (ops→modules allowed —
    composition root); migration **`0015`** partial-unique
    `reimb_claims.workflow_instance_id` (DB belt behind the submit row-lock).
  - **Tests**: 5 new files + 3 extended (46 new/changed) — definition shape pins,
    atomic submit + flag-before-ref + double-submit race (two sessions, one 409, one
    ref), the **no-null-holder property walk** incl. every return loop, segregation
    blocks the chief self-approving, holder-resolution matrix, working-day SLA stamps
    (holiday-aware, calendar-isolated), escalation/ladder idempotency, seed-workflows
    ×2. Pre-existing `test_reference_numbers` absolute `RB-…-0001` asserts made
    rerun-safe (real submits now COMMIT RB allocations).
- **Decisions:** recorded in `docs/modules/reimbursement.md` §5 (2026-07-29 entry) +
  8 delta-register rows; form library react-hook-form + zod (tech-stack §4); My-Work
  → R-2-wizard (master-plan §2 scope note); workflow-standards §8 updated (ladder
  delivery shipped; enqueuer pre-commit caveat documented).
- **Verified:** pytest **413/413** (+36 net), lint-imports 3/3, `alembic check` clean at
  head **`0015`** (upgrade applied live), `seed-rbac`/`seed-workflows`/`load-reference`
  re-runs no-op. FE untouched (gate unchanged from #14).
- **Next:** R-2-wizard (see ▶ NEXT SESSION PROMPT — no open kickoff questions).

### Session 14 — 2026-07-28 — Stage C R-2-shell: the first React surface

- **Phase(s):** C (R-2-shell — the FE-foundation half of R-2-wizard, split in the R-phase
  table) · **Commit:** `session(2026-07-28)` — **local only** (push at the Stage C gate).
- **Done:**
  - **`web/` — the first frontend** (React 19.2.8 + Vite 6.4.3 + Tailwind 4.3.3 +
    TS 5.9.3; exact pins via `.npmrc save-exact` + `engine-strict`; Node **22 LTS**).
    Compose **`web` service** (node:22-alpine, :5174, `node_modules` on the
    `web_node_modules` named volume, `CHOKIDAR_USEPOLLING`, `npm install`-at-boot) with
    the **same-origin `/api` Vite proxy → app:8001 — NO CORS** (api-standards §6 records
    the contract + the CORS-knob deferral). Zero backend/Python changes; head stays `0014`.
  - **Token pipeline** — `theme/tokens.css`: baked neutral `:root` mirror of
    `NEUTRAL_TOKENS` + **`@theme inline`** mapping every Tailwind namespace to
    `var(--oc-*)` (stock palette/type/radius/shadow wiped — tokens-only is structural);
    `theme/tokens.ts` ports `to_css_variables()` and injects the served tree onto `<html>`
    after the config fetch (blocked first paint behind a neutral skeleton; fail-safe =
    neutral tokens + all flags OFF). Tenant re-brand needs no rebuild.
  - **API layer** — `api/http.ts` (the ONE wrapper: `X-Requested-With` on every non-safe
    method incl. login, `credentials: same-origin`, typed `ApiError` from the envelope,
    `Retry-After` + `X-Request-ID` surfaced) + typed clients (`auth.ts`, `config.ts`).
  - **Component inventory seed (14)** in `src/components/<Name>/` — Button, FormField,
    Card, Tabs (Radix), StatusChip, TaskList (GOV.UK), Stepper, Timeline, PipelineCard,
    Dialog (Radix), EmptyState, Skeleton, Toast/bell (Radix + `toast-bus`), ErrorSummary
    (GOV.UK — **added as inventory item 14 by ui-standards §3 amendment**). All 6 layout
    templates in `src/layouts/` (AppShell with `minimal` mode for auth screens).
  - **Auth flows end-to-end** — login (`mfa_token` via navigation state only) → guards
    (`RequireAuth` forced-state chain mirroring `require_session_pending_ok`) → forced
    password change → forced MFA enroll/confirm → home; global 401 → session-expired
    toast + redirect; 429 countdown from `Retry-After`; `password_policy` details mapped
    to actionable field messages. `NAV_GROUPS` seed (flags + roles; intent keywords for
    Stage D); flag-gated `/reimbursement` placeholder (ListPage + EmptyState); DEV-only
    `/ui-foundation` catalog (Storybook = recorded NO).
  - **Docs filled (rule 9 + session-end checklist):** ui-standards §3 (amendment) +
    **§7 FILLED** (structure, Tailwind mapping, Storybook-no, breakpoints, **Lucide**,
    FE QA gate, gating deferral) + §8 (as-built specs) + §9 (rendering half);
    tech-stack §1 (TS/React/Node rows) + §3 (`web` row) + **§4 FILLED** (exact pins,
    prod 6 / dev 23) + §5 (FE gate); api-standards §6 (SPA contract, no-CORS);
    reimbursement.md §2/§3/§4/§5; README (ports, commands, layout); .env.example.
- **Decisions:** kickoff chose the shell over R-4-app; **Lucide** icon set; **Node 22
  LTS**; **Radix UI** primitives (components-dir only); **proxy-not-CORS** (honest
  rationale recorded — CORS could work on localhost same-site, the proxy is simpler +
  production-parity); Storybook NO; Tailwind-default breakpoints; ErrorSummary inventory
  amendment; react-query data layer; roles+flags UI gating (self-permissions deferral);
  **R-0 closed: same-day round trip = 50% (accountant confirmed)**. Deferred: form
  library (wizard session), MFA QR render, bell feed API, pagination envelope (Stage D).
- **Verified:** FE gate green — eslint, `tsc -b`, **vitest 28/28** (incl. axe a11y smokes
  + the guard chain), production build; **pytest 377/377 unchanged**, lint-imports 3/3;
  live smoke via the proxy: `/` 200, `/api/v1/config` 200 (neutral tokens + 3 flags),
  login POST without `X-Requested-With` → **403 csrf_failed**. HMR + named-volume boot
  verified (`docker compose up -d web` → Vite ready in ~400 ms).

### Session 13 — 2026-07-27 — Stage C R-2-engine: the per-diem computation engine

- **Phase(s):** C (R-2-engine) · **Commit:** `session(2026-07-27)` (R-2-engine) — **local
  only** (push cadence confirmed: once at the Stage C gate).
- **Done:**
  - **`core/money.py`** — the platform money convention (parallel to `core/time.py`):
    `to_money()` = `ROUND_HALF_UP` quantize to the centavo, `money_str()` = canonical 2-dp
    string for JSONB. `database-standards.md` §10 updated (rounding mode +
    quantize-components-then-sum + JSONB-money-as-strings).
  - **Migration `0014`** — `reimb_claims.is_within_50km` + `overnight_stay` (attested
    booleans, NOT NULL default false) feeding the 50-km gate. Reversible (down→up verified).
  - **The engine** (`modules/reimbursement/services/` — the module's first service code):
    pure `per_diem.py` (frozen dataclasses, no I/O — per-day breakdown: arrival/full = 100%,
    return/same-day = config 50% [meals+incidentals, no lodging component], host strips
    remove a component if present, 50-km gate, controlling-leg attribution, as-of-day
    rates/regions/configs) + `compute.py::compute_claim_totals(session, *, claim_id,
    other_total, actor_user_id)` (loads, computes, writes leg fields + `totals` JSONB v1
    incl. `days[]`, settlement vs the linked CA; flushes, caller commits, idempotent) +
    `errors.py` (fail-closed `reimb_*` APIError factories).
  - **Tests** — `test_money`, `test_per_diem_engine` (24 pure-core tests incl. the pinned
    **₱5,500 anchor**, cluster switch, strips, 50-km both branches, multi-leg
    no-double-count, rounding, mid-trip rate change, error codes, settle matrix),
    `test_per_diem_service` (8 integration tests on `app_session`), `make_leg` helper +
    `tests/reimbursement_trip_factories.py` (9 representative trips — the R-1 deferral).
- **Decisions:** per-day unit attributed to the controlling leg (no day table — breakdown
  in `totals["days"]`, promotion path R-5); 50-km = fare-only without overnight (supersedes
  spec §8's lodging-only strip); same-day trip = 50% (R-0 accountant confirmation added);
  gov-vehicle leg with a fare = hard 422; `per_diem_pct` stores the day-type gross. Full
  rationale: `docs/modules/reimbursement.md` §2 + §5.
- **Verified:** pytest **377/377 (+37)**, lint-imports 3/3, `alembic` head `0014`,
  `0013↔0014` reversible. **No new dependency.**

### Session 12 — 2026-07-27 — Stage C R-1: reimbursement model + config pack

- **Phase(s):** C (R-1) · **Commit:** `session(2026-07-27)` (R-1) — **local only**.
- **Done (one migration `0013`, autogenerated then hand-tuned):**
  - **Core reference-number service #5** — `core/models/reference_sequence.py`
    (`core_reference_sequences`) + `core/reference_numbers.py::allocate_reference_number`
    (`FOR UPDATE`-locked `(scope, year)` counter → `RB-`/`LQ-YYYY-NNNN`, yearly reset,
    never reused). Was unbuilt; reimbursement is first consumer.
  - **13 `reimb_*` tables** (`office_connect/modules/reimbursement/models/`, grouped
    package) — `reimb_claims` (+ `workflow_instance_id` FK INTO `core_workflow_instances`,
    `destination_region_code` replacing `destination_class`), `reimb_itinerary_legs`,
    `reimb_cash_advances` (+ **CA hard-block** partial-unique per claimant, PD 1445 §89),
    `reimb_dte_clusters` + `reimb_region_clusters` (EO 77 3-cluster, effective-dated),
    `reimb_configs`, `reimb_checklist_catalogs`/`_items`, `reimb_return_reason_catalogs`,
    `reimb_return_events`/`reimb_status_histories`/`reimb_external_events` (append-only +
    REVOKE UPDATE + audited), `reimb_attachments` (core-attachments join). Migration `0013`
    tuned for append-only grants + enum-drop-on-downgrade; `alembic/env.py` imports the
    module models.
  - **Seeds** (`modules/reimbursement/seeds.py`, module-local — core can't import modules):
    config pack with legal sources, EO 77 3-cluster rates, all 17 PSGC regions → cluster,
    a representative COA-2023-004 checklist, return-reason taxonomy.
  - **Tests** — `test_reference_numbers`, `test_reimbursement_schema` (CA hard-block, ref_no
    partial-unique), `test_reimbursement_seeds` + extended `test_migrations`/`test_append_only`.
- **Decisions:** dropped `reimb_approval_steps` (= `core_workflow_steps`); deferred
  `reimb_signatory_configs` → R-4-app + `reimb_template_maps` → R-5 (Rule 10);
  `destination_class` → `destination_region_code`; CA hard-block = DB constraint (not a
  workflow guard); ref-numbers built as core #5; append-only reimb logs audited; 30-day clock
  = `calendar` (COA 97-002); computation logic deferred to R-2; fixtures trimmed to
  config/catalog seeds. See `docs/modules/reimbursement.md` §5.
- **Verified:** **pytest 340/340 (+20)**, **lint-imports 3/3** (module imports core only),
  migration `0012↔0013` idempotent + reversible.
- **Docs updated:** reimbursement.md (R-1 done + delta rows + decisions), database-standards.md
  §12 (ref-number service), master-plan.md §1.1 #5 (SHIPPED), CHANGELOG.md `[Unreleased]`,
  this file.
- **Next:** Stage C — R-2 per-diem computation engine / the React shell / R-4-app (confirm at
  kickoff; see the Next Session Prompt).

### Session 11 — 2026-07-27 — Stage C: the shared core workflow engine (R-4 core, pulled forward)

- **Phase(s):** C (Stage C first code increment) · **Commit:** `session(2026-07-27)`
  (Stage C) — **local only** (Stage C pushes at its QA gate).
- **Kickoff decisions (user-confirmed):** first Stage-C increment = **the engine**
  (foundation-first — pure backend, highest Rule-10 leverage, unblocks R-1's
  `reimb_claims.workflow_instance_id` FK); **delegation = a first-class
  `core_workflow_delegations` table** (on-behalf-of; refines B3 — master-plan §1.1 #1
  outranks the module-doc "no table" note); FE stack for the later shell = **React 19 +
  Vite 6 + Tailwind 4 + TypeScript, headless primitives (Radix/Headless UI) on `--oc-*`
  tokens** (lands in ui-standards §7 + tech-stack §4 when the scaffold is built).
- **Done (one migration `0012`; the rest app-layer, all in `core/`):**
  - **Schema** — `core/models/workflow.py`: 6 enums + 8 tables. Design-time (business):
    `core_workflow_definitions` / `_definition_versions` (immutable once published) /
    `_states` (approval-gate config: `required_permission`, `join_type`, `step_count`,
    `quorum_count`, `sla_hours`, `enforce_segregation`) / `_transitions` (typed guards:
    `min/max_amount`, `required_permission`, `requires_comment`; `required_role_id`
    reserved unwired). Runtime (business): `_instances` (pinned version, `row_version`
    CAS, `revision_no`, polymorphic `(subject_kind, subject_id)` no-FK back-ref,
    `amount`/`context` guard inputs) / `_steps` (per-approver fan-in rows, `revision_no`-
    scoped, `sla_due_at`). History: `_events` (**append-only + audited**, REVOKE UPDATE,
    `payload` `__audit_exclude__`; partial-unique `(instance,idempotency_key)` and
    `(step,escalation_level)`). Delegation (business): `_delegations`.
  - **Service** — pure `core/workflow/`: `definitions` (author + `validate_graph` +
    one-way `publish_version` + `get_published_version`); `transitions.execute_action`
    (the heart — FOR-UPDATE lock → idempotency replay → CAS 409 → typed-guard routing →
    `resolve_authority` (org-scope + delegation) → `assert_segregation` → step fan-in by
    `join_type` → state move + `row_version` bump → activate next gate + stamp SLA →
    append audited event) + `available_actions`; `steps` (activate/`join_satisfied`);
    `delegation.resolve_authority`; `replay.fold_events`/`is_consistent`;
    `sla.sweep_due_steps` + `register_sla_enqueuer`; `service.start_instance` (the flag
    gate); `errors` (structured `APIError` codes).
  - **Seeds/seams** — `workflow.definition.read/manage/publish` + `workflow.instance.read`
    + `workflow.delegation.manage` (auditor gets the reads); `ops/workflow_tasks.py`
    (`ops.sweep_workflow_sla`, ops→core injection) + beat schedule (*/5 min); flag gate in
    `start_instance`.
  - **Docs** — NEW `docs/standards/workflow-standards.md` (the engine contract, 7
    consumers); `database-standards.md` §6 (audited-vs-unaudited append-only note);
    `foundation.md` §7 (Stage-C decision record incl. the B3-delegation refinement);
    `reimbursement.md` (delta + R-4 status: engine core done, R-4-app remaining);
    `master-plan.md` §1.1 #1 + §2 R-4 (SHIPPED + delegation delta).
- **Verified:** **pytest 320/320 (+34** across definitions/transitions/maker-checker/
  scope/delegation/return-reject/replay/sla/flag/concurrency + extended append-only &
  migrations), **lint-imports 3/3** (engine pure core; the ops→core SLA seam is the only
  cross-boundary edge and lives in ops), migration `0011↔0012` idempotent + reversible.
  The concurrency test drives two real sessions at one instance — exactly one approve wins,
  the other gets a 409.
- **Decisions:** see `docs/standards/workflow-standards.md` + `docs/modules/foundation.md`
  §7 (Stage C). Engineering calls: permission-string authz (not role ids); CAS via row
  lock + audited ORM mutate; events audited append-only; fan-in `revision_no`-scoped; SLA
  first cut = one idempotent escalation (ladder/delivery deferred to R-4-app).
- **Docs updated:** workflow-standards.md (new), database-standards.md, foundation.md,
  reimbursement.md, master-plan.md, CHANGELOG.md `[Unreleased]`, this file.
- **Next:** Stage C next increment — **R-1 (reimbursement model + config pack)** or **the
  React shell** (confirm at kickoff; see the Next Session Prompt).

### Session 10 — 2026-07-27 — Stage B Increment 4 (wire seams + directory + compliance) + phase-2 gate

- **Phase(s):** 2 / Stage B (B4) — **closes Stage B** · **Commit:** `session(2026-07-27)`
  (`b3d150c`) — **pushed** to `origin/master` + annotated tag `phase-2-complete`
  (Stage B's first push; credential `avincentpatrick`).
- **Kickoff decisions (user-confirmed):** notification prefs = dedicated
  `core_notification_preferences` table (migration `0011`) + `suppressed` status,
  security/transactional bypass; person-field SPI = **direct identifiers only**
  (`core_staff` names/email + notification recipient/body/payload; **keep**
  `core_users.email` + `employee_no`/position/plantilla/status); query-log scope = all
  `/api/v1` (reads + writes, incl. anonymous) minus `/config` + OPTIONS; phase-2 push =
  **prepare then pause** (D4); CSS-IS ingestion = build the mechanism, run on synthetic
  fixtures; attachments = coarse RBAC + a Stage-C holder-scoping seam.
- **Done (one migration `0011`; the rest app-layer):**
  - **Attachments HTTP router** (`core/api/attachments.py`) — `POST /attachments`
    (multipart, size-capped chunked read → 413, magic-byte validated → 422, `pending`),
    `GET /{id}` metadata, `GET /{id}/content` (streaming, EXIF-stripped derivative,
    `nosniff`), `DELETE /{id}` (soft delete), `GET /disposal-report`; `attachment.*`
    gates seeded (staff upload/read/download · approver read/download · auditor
    read+dispose). **Per-upload scan enqueue** (`core/attachments/scan_queue.py`,
    after-commit drain; ops registers the Celery `send_task` — core stays pure; beat
    sweeper backstops). **Holder-auth seam** (`core/attachments/authz.py`,
    `register_holder_authorizer`, empty in B4). `DownloadNotReady→409`.
  - **Notification recipient/prefs** — `core/notifications/recipients.py`
    (`resolve_recipient`: `user_id→core_users.email`, staff-email fallback; opt-out via
    `core_notification_preferences`; security/transactional bypass; unresolvable →
    `suppressed`), called inside `persist_notification` (signature unchanged); `dispatch`
    treats `suppressed` as terminal. New model + migration `0011` (+ `suppressed` enum).
  - **CSS-IS directory ingestion** — pure `core/directory/ingest.py` (atomic upfront
    validation, Kahn topological org insert, tombstone restore, leave-alone absence
    policy + guarded prune shipped OFF); `POST /api/v1/directory/import` + read
    endpoints (`core/api/directory.py`); `bootstrap ingest-directory` CLI; `load-fixtures`
    refactored onto the same service (one code path).
  - **Admin provisioning** — `core/api/users.py`: `POST /users` (create-from-staff,
    temp password + forced change, no self-registration), `GET` list/`{id}`,
    `POST /{id}/deactivate` (`SessionStore.destroy_all_for_user` + `user.deactivated`
    event; self + break-glass `409`-protected), `POST /{id}/reactivate`.
  - **Query-log middleware** — `core/api/query_log_middleware.py` (innermost; own pooled
    `SessionLocal`; ids/param-names/status only, never bodies/values; `query_log_enabled`
    flag; log-and-continue on failure) wired in `main.py`.
  - **Person-field SPI redaction** — `__audit_exclude__` on `core_staff`
    (names + email) and `NotificationOutbox` (`recipient_email`/`body_text`/`payload`);
    `core_users.email` kept (login handle). No endpoint change (auditor timeline shows
    `[redacted]` by design).
  - **Stage-B PIA** (`docs/compliance/pia-stage-b-identity.md`) + processing-register
    row (NPC Advisory 2017-03). **Dep** `python-multipart==0.0.20` (image rebuilt).
- **Verified:** **pytest 286/286** (+48 across attachments-API/notification-recipients/
  directory-ingest/provisioning/query-log/spi-redaction + a bootstrap CSV-parse test),
  **lint-imports 3/3** (core never imports ops/worker/modules — the ops→core scan
  enqueuer injection is the only cross-boundary edge, and it lives in ops), migration
  chain `0001→0011` reaches head, idempotent + reversible (downgrade 0011→0010 →
  re-upgrade clean; `ADD VALUE IF NOT EXISTS 'suppressed'` is add-only). ASGI client
  tests exercise the full live stack (login + MFA + CSRF, real Postgres + Redis db 4):
  upload→scan→download with EXIF stripped, 403/422/413/409 mappings, opt-out
  suppression, deactivate revoking sessions, query-log rows with no values, and the
  redacted-yet-verifying audit chain.
- **Decisions:** see `docs/modules/foundation.md` §7 (Stage B Increment 4).
- **Docs updated:** foundation.md (§5 B4 done + §7 B4 record), api-standards.md (§5 +
  new §8), tech-stack.md (`python-multipart`), CHANGELOG.md (promoted to `0.2.0`),
  `office_connect/__init__.py` (`APP_VERSION 0.2.0`), docs/compliance/ (PIA + register),
  this file.
- **Next:** Stage C — Reimbursement vertical + core workflow engine + first React
  shell (see the Next Session Prompt).

### Session 9 — 2026-07-23 — Stage B Increment 3 (RBAC enforcement)

- **Phase(s):** 2 / Stage B (B3) · **Commit:** `session(2026-07-23)` — **local
  only** (Stage B pushes at its QA gate, tag `phase-2-complete`, after B4).
- **Kickoff decisions (user-confirmed):** delegation/OIC via
  `core_user_roles.valid_from/to` **only, no table** (resolves master-plan §2 vs
  foundation §5); maker-checker = **reusable core helper + tests now**, DB-level
  constraint deferred to Stage C (approval table doesn't exist yet); auditor report
  = **printable HTML + JSON**; permission cache = **version-keyed + boundary-aware
  TTL + in-place live-session bump, no pub/sub**. Engineering call: unscoped
  `require_permission` semantics kept unchanged (any active grant confers) — the
  global-only tightening defers to Stage C.
- **Done (no migration — identity schema complete since B1):**
  - **`core/auth/permission_cache.py`** — `PermissionCache` (injected db-4 Redis),
    key `authz:perm:{uid}:v{permissions_version}`, JSON code-set, `get_or_load`
    (loader runs only on a miss → cache hit = no DB hit), TTL capped at the next
    valid-window edge, `invalidate`.
  - **`core/auth/dependencies.py`** — `require_permission(perm, scope=GLOBAL)`
    rewired behind its frozen signature: GLOBAL = cached membership; REQUESTER =
    uncached `authorize_scoped`. New `get_permission_cache`, `load_permission_entry`
    (codes + next boundary). `effective_permissions` kept.
  - **`core/org_units.py`** — `ancestors_or_self` recursive `parent_org_unit_id`
    CTE (depth-guarded, first ancestry walker), `scoped_org_units`, `authorize_scoped`
    (global grant, or a scoped unit covering the request's subtree); `OrgUnitScope`.
  - **`core/maker_checker.py`** — `assert_segregation` (no self-approval / distinct
    DV-Box A/B/C approvers, `409 segregation_of_duties`).
  - **`core/rbac.py`** — `grant_role`/`revoke_role`: upsert/restore or soft-delete
    `core_user_roles`, bump `permissions_version`, `set_permissions_version` on live
    sessions (post-commit), emit `rbac.role.granted/revoked` chain events.
  - **`core/api/rbac.py` + `core/api/audit.py` + schemas** — RBAC admin (grant/
    revoke + role/permission/user-role reads) and auditor (`/audit/verify` printable
    HTML+JSON PASS/FAIL, `/audit/records/{table}/{pk}` timeline); routers mounted.
  - **Seams touched** — `session_store.set_permissions_version` (Lua-guarded HSET),
    `audit.append_auth_event` (+ optional `table_name`/`row_pk`), `config.py`
    (`authz_cache_backstop_seconds`), `main.py` (cache on `app.state`).
- **Verified:** **pytest 238/238** (+25 across permission-cache/org-scope/maker-
  checker/rbac-enforcement/audit-report), **lint-imports 3/3** (all new code in
  `core`, boundary held). No new dependency, no migration. The ASGI client tests
  exercise the full live stack (real middleware, Redis db 4, Postgres) — grant/
  revoke landing on the next request, org-subtree denial, auditor read-only, and a
  printable PASS report are all covered end-to-end.
- **Decisions:** see `docs/modules/foundation.md` §7 (Stage B Increment 3).
- **Docs updated:** api-standards.md (§5 + new §7 AuthZ contract), foundation.md
  (§1/§5/§7), CHANGELOG.md, this file.
- **Next:** Increment B4 — wire seams + directory + compliance + phase-2 QA gate
  (see the Next Session Prompt).

### Session 8 — 2026-07-23 — Stage B Increment 2 (authentication)

- **Phase(s):** 2 / Stage B (B2) · **Commit:** `session(2026-07-23)` — **local
  only** (Stage B pushes at its QA gate, tag `phase-2-complete`, after B4).
- **Kickoff decisions (user-confirmed):** single-tenant auth (no `tenant_id`) —
  B1 revisit note resolved; logout/session-revoke recorded as **hash-chained
  semantic rows** (`append_auth_event`) not log-only; sessions on **Redis db 4**
  (the briefed db 3 collides with GlitchTip); **researched session defaults**
  (12h absolute / 30-60min idle / cap 3). Engineering calls: force-MFA-enrollment
  (not hard block), two-step MFA, minimal DB-backed `require_permission` now,
  committed gzipped top-100k blocklist.
- **Done (no migration — identity schema complete):**
  - **`core/auth/` package** — `session_store` (Redis Hash `session:{id}` +
    per-user ZSET, opaque 256-bit id, absolute/idle TTL, cap eviction, lazy index
    prune, rotate), `policy` (pure timeout/tier math), `principal` (DB-free
    request principal), `password_policy` (NIST 12+/no-composition/no-rotation +
    NFKC + blocklist + context-word checks; recorded deviation), `throttle`
    (per-account + per-IP backoff, enumeration-parity), `mfa` (pyotp TOTP, skew,
    single-use replay guard), `verifiers` (break-glass-above-LDAP branch),
    `service` (login/MFA/logout/change-password state machine with dummy-hash
    timing parity), `middleware` (CSRF + auth-principal), `dependencies`
    (`require_session`/gates/`require_permission`/`require_reauth`).
  - **`core/api/`** — `auth.py` (login/logout/me/password.change/mfa.enroll/
    confirm/verify/own+admin session mgmt/admin reset; cookie set/clear),
    `errors.py` (first structured error-envelope handlers + `APIError`),
    `schemas/auth.py` (first Pydantic wire models); router mounts `auth`.
  - **Wiring** — `config.py` (core-local `redis_db_url` twin + session/cookie/
    throttle/MFA settings + resolver properties), `main.py` (session-Redis client +
    `SessionStore` on `app.state`, CSRF + auth middleware, `register_error_handlers`),
    `db.py` (`get_session` injects `actor_id` from `request.state.user`),
    `audit.py` (`append_auth_event` — hash-chained `action=insert` `core_sessions`
    row within the CHECK, forbidden-key guard). `.env.example` auth block.
  - **Blocklist** — vendored SecLists `Pwdb_top-100000.txt` gzipped
    (`core/security/blocklists/`, ~432 KB, provenance README, `.gitattributes`
    binary+vendored), lazy `frozenset`. **Dep**: `pyotp==2.9.0`.
- **Verified:** **pytest 213/213** (was 155; +58 across policy/blocklist/mfa/
  throttle/session-store/login-flow/mfa-flow/password-change/audit-events/csrf/
  redis-config), **lint-imports 3/3** (the `core ↛ ops` boundary held via the
  core-local URL helper); live curl walkthrough — login sets an HttpOnly cookie,
  wrong-vs-unknown are byte-identical 401s, 5 fails → 429, logout destroys the
  server record, MFA two-step, password-change revokes other sessions; the login
  `last_login_at` UPDATE carries the real `actor_id`, logout/revoke append valid
  chain rows with no credential, `verify_chain` intact.
- **Decisions:** see `docs/modules/foundation.md` §7 (Stage B Increment 2).
- **Docs updated:** foundation.md (§1/§5/§7/§8a), api-standards.md (§2/§5 + new
  §6 session/CSRF contract), tech-stack.md (pyotp + db-4 map + vendored blocklist),
  requirements.txt, CHANGELOG.md, `.env.example`, this file.
- **Next:** Increment B3 — RBAC enforcement (see the Next Session Prompt).

### Session 7 — 2026-07-23 — Stage B Increment 1 (identity schema + deferred-FK closure)

- **Phase(s):** 2 / Stage B (B1) · **Commit:** `session(2026-07-23)` — **local
  only** (Stage B pushes at its QA gate, tag `phase-2-complete`, after B4).
- **Kickoff decisions (user-confirmed):** identity = **split** (`core_staff`
  directory + `core_users` auth); directory seed **decoupled from CSS-IS**
  (separate system, inbound feed later; synthetic dev fixtures now); audit-payload
  SPI = **IDs + field names only** (credential subset executed now); scope =
  detail B1, roadmap B2–B4.
- **Done (migrations 0009–0010):**
  - **Identity tables** — self-ref `core_org_units` (office/division/section/unit);
    `core_staff` (plantilla directory, superset); `core_users` (auth,
    nullable `staff_id` FK, MFA columns pre-built for B2); `core_roles`,
    `core_permissions`, `core_role_permissions`; org-scoped `core_user_roles`
    (**PG16 `NULLS NOT DISTINCT`** grant uniqueness + `valid_from/to` for B3);
    append-only `core_login_attempts` (anti-enumeration, REVOKE UPDATE).
  - **Deferred-FK closure (`0010`)** — the single "core_users referential
    closure": `created_by`/`updated_by`/`deleted_by` (mixin, all 18 business/
    lookup tables) + bespoke `actor_id`/`recipient_user_id`/`disposed_by`/
    `generated_by`/log `created_by` → `core_users`; `division_id`/`section_id` →
    `core_org_units`; `tenant_id` → `core_tenant_configs`. Sanctioned no-FK
    (`core_attachments.holder_*`, `core_audit_logs.row_pk`) left alone. All
    pre-existing `*_by` are NULL → validated with no backfill.
  - **Credential redaction** (pulled forward from B4) — `core_users.__audit_exclude__
    = {password_hash, mfa_secret}`; the audit listeners write `[redacted]` (field
    name kept, value withheld) on INSERT + UPDATE, so a secret never seals into
    the immutable chain (database-standards §7).
  - **Argon2id hasher** (`core/security/password.py`, `argon2-cffi`; params in
    tech-stack.md). **RBAC seeds** — permission (27) + role (4) `SeedDataset`s in
    `REGISTRY` + a bespoke grant resolver (`core/seeds/rbac.py`, 41 grants,
    tombstoned revocations). **Bootstrap** — new `seed-rbac` + `promote-admin`
    (break-glass login from `settings.bootstrap_admin`, temp password once);
    `load-fixtures` now also seeds a synthetic org tree + staff.
- **Verified:** **pytest 155/155** (was 132; +23), **lint-imports 3/3**; full
  chain `0001→0010` idempotent (×2) + downgrade-to-base → re-upgrade clean; FK
  closure asserted (`test_identity_schema`); `oc_app` denied UPDATE/DELETE on
  `core_login_attempts` + no DELETE on any identity table; RBAC seed idempotent +
  every-permission-exists gate; break-glass promotion idempotent + temp password
  verifies; `password_hash`/`mfa_secret` `[redacted]` in the chain (INSERT +
  UPDATE) with `verify_chain` intact.
- **Decisions:** see `docs/modules/foundation.md` §7 (Stage B Increment 1).
- **Next:** Increment B2 — Authentication (see the Next Session Prompt).

### Session 6 — 2026-07-23 — Stage A Increment 4 (spine amendments) + Phase 0 gate ✅

- **Phase(s):** 0 / Stage A (closes Phase 0) · **Commit:** `session(2026-07-23)`
  (`74a9a7a`) + docs commits; tag `phase-0-complete` — **pushed to `origin`**
  (first push, after re-auth as `avincentpatrick`)
- **Done (migrations 0003–0008, built in independently-committable groups):**
  - **Activity taxonomies** — `core_activity_tags` (configurable GAD/CCET/DRR/UHC
    vocabulary, never boolean cols) + `core_activity_tag_assignments` (multi-tag
    link).
  - **UACS/PREXC** — `core_pap_codes` (per-FY tree, self-ref parent,
    effective-dated) + `core_object_codes` (travel = 5-02-01-010-00); UACS
    never-reuse (deactivate, effective-date a revision).
  - **Holiday + working-day engine** — `core_holidays` + pure `core/workdays.py`
    (weekend/holiday/suspension math, unit-tested) + DB loader.
  - **Compliance calendar** — `core_compliance_deadlines`, the 22 §3.4 statutory
    deadlines as effective-dated, tenant-overridable data (two partial-unique
    indexes: platform default vs tenant override).
  - **Attachments service** (`core_attachments` + `core/attachments/`) — magic-byte
    allowlist (JPEG/PNG/WebP/PDF; SVG rejected) → SHA-256 content-address →
    **injectable fail-closed scanner** (NullScanner deny-in-prod/clean-in-dev +
    ClamAVScanner) → Pillow re-encode + EXIF/XMP strip + HEIC→JPEG; dual SHA
    (original evidence + sanitized derivative served for images); retention
    (`retention_class`/`legal_hold`, no auto-purge, disposal report); deferred
    Celery scan task (`ops/`) + beat sweeper; **auth-checked download = a service
    method with an `authorize` hook** (HTTP router defers to Stage B).
  - **Notification outbox** — replaced the Inc-3 stub body: `core_notifications`
    (outbox + in-app center via a channel discriminator) + append-only
    `core_notification_deliveries` (dead-letter/failed-jobs); `send_notification`
    persists + dispatches (inline default; app enqueues to the worker in celery
    mode after commit, via an injected enqueuer — core stays Celery-free); dedup;
    Celery retry/back-off → dead. Signatures unchanged.
  - **Report lineage** — `core_report_lineages` (append-only, unaudited) +
    `record_lineage` helper (Blueprint #17).
  - **Seed framework** — `core/seeds/` datasets (owner + cadence) + `ops`
    `load-reference`: idempotent, environment-aware upsert; loaded tags/codes/
    holidays/deadlines (re-run = 0 changes; loads under production).
  - **Observability** — stdlib JSON logs + request-id contextvar (uvicorn routed
    through it) + fail-safe optional error tracker (`sentry-sdk`/GlitchTip);
    `docs/standards/api-standards.md`; `docs/compliance/` (PIA, register, breach
    runbook, retention) + expanded `docs/operations/` runbooks.
  - Compose: `clamav` (profile `clamav`) + GlitchTip (profile `observability`) —
    neither in default `up`/CI. Deps: Pillow, pillow-heif, clamd, sentry-sdk.
- **Verified:** **pytest 132/132** (was 68; +64), **lint-imports 3/3**; full chain
  `0001→0008` idempotent (×2) + downgrade-to-base → re-upgrade clean; attachment
  upload→scan→download round-trip with EXIF stripped on the served copy, and
  fail-closed rejects (infected/oversized/SVG/bad-magic/pending); notification
  dispatch inline **and** celery→worker end-to-end (`ops.dispatch_notification`
  registered, row → `sent`); `oc_app` denied UPDATE/DELETE on both new append-only
  tables; `load-reference` idempotent + prod-safe; `/health` healthy;
  `/api/v1/config` fail-safe OFF; JSON logs carry the request id; Laragon
  untouched.
- **Decisions:** see `docs/modules/foundation.md` §7 (attachments full-pipeline +
  ClamAV-opt-in; retention ≠ soft delete; outbox signature-stable; effective-dated
  never-boolean data; pure WD engine; report lineage append-only+unaudited;
  seed-framework cadences; observability logs-now/tracker-profile).
- **Phase 0 QA gate:** manual test guide added (foundation.md §8); CHANGELOG
  promoted to **0.1.0**; `APP_VERSION` bumped `0.1.0.dev1 → 0.1.0`; tagged
  **`phase-0-complete`**; **first push** of `master` + tags to `origin` landed
  (the cached credential was the wrong account — `icvpitahc`, 403 — so it was
  cleared and re-authenticated as `avincentpatrick`; `git ls-remote` confirms
  `origin/master` = `5eb19a4` + the tag).
- **Docs updated:** foundation.md (§1/§4/§6/§7/§8), tech-stack.md (deps/services/
  CLI/external), database-standards.md (§8 effective-dated + tenant-override),
  api-standards.md (new), docs/compliance/ (new, 5 files), docs/operations/
  (4 new runbooks), CHANGELOG.md, this file.
- **Next Session Prompt (archived):** Stage B (Phase 2) — Identity & Access —
  full text in the top block as of this session.

### Session 5 — 2026-07-23 — Stage A Increment 3 (integrations + bootstrap) ✅

- **Phase(s):** 0 / Stage A · **Commit:** `session(2026-07-23)` — local
- **Done:**
  - **Storage driver abstraction** (`office_connect/core/storage/`):
    `StorageDriver` ABC (content-addressed by SHA-256; `save`/`open`/`read`/
    `exists`/`delete`), **`LocalVolumeStorageDriver`** (the prod default —
    sharded `ab/cd/<sha256>` store, atomic `.partial`→`replace` + fsync,
    dedup; bind-mounted `./storage`→`/app/storage`), **`GoogleDriveStorageDriver`**
    (lazy client, **Shared-Drive verification** — refuses My Drive folders),
    `get_storage_driver()` factory on `STORAGE_DRIVER`.
  - **Email drivers** (`core/email/`): `EmailDriver` ABC + shared MIME builder;
    **SMTP** (stdlib `smtplib`, STARTTLS, the default transport), **Gmail API**
    (lazy client, domain-wide delegation, base64url send), **log** (dev
    fail-safe — records, doesn't send); `get_email_driver()` auto-selects
    `smtp` if `SMTP_HOST` set else `log`.
  - **Notification outbox stub** (`core/notifications/`, core-service #4 seam):
    `send_notification()` routes email events through the selected driver now;
    `send_test_email()` is the Increment-3 test-email path. Durable outbox
    table + retry + notification center flagged for Increment 4 (signature
    stable — Rule 10, no duplication).
  - **Design-token contract** (`core/ui/tokens.py`): `NEUTRAL_TOKENS` (WCAG-AA
    palette + 4-px spacing + type scale + shape) as the single source of truth,
    `build_tokens(branding)` deep-merges `branding.tokens` overrides (unknown
    keys ignored), `to_css_variables()` → `--oc-*`. Served under `tokens` in
    `GET /api/v1/config` — always present (neutral even under the DB fail-safe).
  - **Bootstrap CLI** (`office_connect/ops/bootstrap.py`): `init` (idempotent
    tenant + module flags), `create-admin` (records admin into the non-public
    `core_tenant_configs.settings` bag for Stage B; not a login), `load-fixtures`
    (synthetic activities, **refused in production**), `send-test-email`. DB
    writes via `oc_app`/`OCSession` (audited); async-from-sync per restore_drill.
  - **Migration 0002**: non-public `core_tenant_configs.settings` JSONB (never
    served by `/api/v1/config`); `settings` mapped on `TenantConfig`.
  - Deps: `google-api-python-client` 2.156.0 + `google-auth` 2.37.0 +
    `google-auth-httplib2` 0.2.0 (pure-Python, lazy-imported); storage bind
    mount + `STORAGE_DRIVER`/`STORAGE_DIR` env on app+worker; `.gitignore`
    `storage/`; `.env.example` driver settings.
- **Verified:** **pytest 68/68** (was 31; +37 across storage/email/notifications/
  tokens/config/bootstrap); **lint-imports 3/3**; migration 0002 idempotent (x2)
  + downgrade→re-upgrade clean; bootstrap CLI init/create-admin/load-fixtures/
  send-test-email all work end-to-end; `load-fixtures` refuses `APP_ENV=production`;
  local storage round-trips a real file (host `./storage` + container);
  `/api/v1/config` serves `tokens` and does **not** leak `bootstrap_admin`/the
  admin email; `/health` healthy; Laragon `dev_pims` untouched.
- **Decisions:** see `docs/modules/foundation.md` §7 (local-volume storage
  default; Google drivers fully built + lazy; create-admin deferred to Stage B
  via non-public `settings`; tokens = neutral defaults + branding merge).
- **Docs updated:** foundation.md (§1 status, §6 gates, §7 decisions), ui-standards.md
  (§2 note + §9 partial-fill), tech-stack.md (google deps + drivers + bootstrap
  CLI), database-standards.md (§11 `settings` bag), master-plan.md (§4 #3
  resolved), CHANGELOG.md, this file.
- **Git remote:** unchanged — provisioned, **still no push**; first push fires
  when Increment 4 passes the Phase 0 QA gate (push-per-phase).
- **Next Session Prompt (archived):** Stage A Increment 4 (spine amendments) —
  full text in the top block as of this session.

### Session 4 — 2026-07-23 — Stage A Increment 2 (ops) ✅

- **Phase(s):** 0 / Stage A · **Commit:** `session(2026-07-23)` — local
- **Done:**
  - **Backup + proven-restore drill** (`office_connect/ops/`): `pg_dump -Fc` as
    the owner role → `office_connect/backups`; restore-drill creates a scratch
    DB, `pg_restore`s, and re-runs `verify_chain()` — seeding a real ≥3-link
    audited chain first so the check is never vacuously green; hard scratch-name
    guard; `--force` cleanup. CLI: `python -m office_connect.ops
    {backup,restore-drill,backup-and-drill}`.
  - **Celery worker + single beat** (`office_connect/worker.py`, compose
    `worker`+`beat`): Redis transport (broker db 1 / results db 2), nightly
    backup task; verified running end-to-end via the broker.
  - **Explicit-step migrations**: `alembic upgrade head` as a deploy step;
    migration-on-boot demoted to a dev-only, env-gated (`OC_MIGRATE_ON_BOOT`),
    **advisory-locked** convenience in a container entrypoint (once per
    container; refused when `APP_ENV=production`). New `core/migrate.py`.
  - **Deploy guard** (`office_connect/ops/deploy_guard.py`, `--mode dev|release`)
    + `scripts/deploy.ps1` dev wrapper + `docs/operations/{deploy,backup-restore}.md`
    POSIX-sh runbooks.
  - Image: `postgresql-client-16` (PGDG, base-codename-derived) + `ENTRYPOINT`;
    `.gitignore` (backups/dumps/pgpass), `.gitattributes` (LF for `*.sh`),
    `.dockerignore` (entrypoint allowed through); new import-linter contract
    "core never imports ops or worker".
  - **Bugs caught & fixed during verification:** base image moved to Debian
    trixie (dropped the bad `bookworm-pgdg` repo); pg client 17-vs-server-16
    `transaction_timeout` restore failure (pinned client to 16); `str(URL)`
    password masking broke asyncpg scratch-DB auth (`render_as_string(
    hide_password=False)`); `scripts` excluded by `.dockerignore`.
- **Verified:** wiped-volume deploy both ways (explicit step + dev-convenience
  boot migration) → healthy, read-write, schema at 0001; `backup-and-drill` →
  audit_rows=3, verify=ok, scratch dropped, dump on host; backup task via broker
  → succeeded; **pytest 31/31**; **lint-imports 3/3**; deploy guard passes
  `--mode dev`, blocks `--mode release` on the `.dev1` version.
- **Decisions:** see `docs/modules/foundation.md` §7 (pg-client major match,
  owner-role backups, seed-before-drill, hide_password, Redis db separation,
  single beat, entrypoint boot-migrate, GitHub-private remote / second-disk
  backup target).
- **Docs updated:** foundation.md, tech-stack.md, CHANGELOG.md, this file; new
  `docs/operations/deploy.md` + `backup-restore.md`.
- **Git remote:** provisioned post-commit — `origin` →
  `github.com/avincentpatrick/office_connect` (`git ls-remote` verified, **no
  push**); first push fires at the Phase 0 / Increment-4 gate (push-per-phase).
- **Next Session Prompt (archived):** Stage A Increment 3 (integrations +
  bootstrap) — full text in the top block as of this session.

### Session 3 — 2026-07-23 — Comprehensive Master Plan v1 ✅

- **Phase(s):** planning (all stages) · **Commit:** `session(2026-07-23)` — local
- **Done:**
  - Two deep-research rounds (18 structured digests, archived in
    `docs/research/` with index): round 1 = engineering/platform practices
    (EO 77/COA rules, workflow engines, auth/NIST, modular monolith,
    attachments, gov UI, on-prem ops, DPA/retention, gap critic); round 2 =
    PH government standards for the new modules (CSC SPMS, DBM WFP/BED/BAR/FAR,
    RA 12009 PPMP/APP, GAM supply/property, ISO 9001 §7.5/§9.3, UACS/PREXC,
    ARTA CSM/FOI/NAP corrections, gap critic).
  - **`docs/master-plan.md` v1**: connectedness contract + core-services
    registry + connection matrix; stages A–I + Wave 2 with old-phase mapping;
    compliance/ops/training tracks; consolidated statutory calendar; open
    decisions register; reference-corrections ledger.
  - **Owner scope additions**: Calendar of Activities (connected surface),
    Controlled Document Management, Supply Management, WFP+PPMP, Performance &
    Deliverables; **DMWIS renamed → DTWIS** (`dtwis_` prefix registered).
  - New module docs: `qms.md`, `supply.md`, `planning-budget.md`,
    `performance.md`; `dmwis.md` → `document-tracking.md`; research-driven
    updates to reimbursement (delta register: EO 77 3-cluster DTE, COA
    2023-004, GAM form numbers, CA hard-block…), foundation (Inc 2 revised:
    explicit-step migrations, 3-2-1 backups; Inc 4 spine amendments added),
    landing (R-2 shell decision resolved; Calendar surface), css-is (ARTA
    v2023 scoring/deadline corrections), admin, reports.
  - Standards: prefix registry extended (`dtwis_`, `qms_`, `supply_`,
    `plan_`, `perf_`); **Rule 10 "shared service first"** added to
    development-workflow.md; soft-delete ≠ records-disposition + audit-payload
    SPI policy notes in database-standards.md; tech-stack production substrate
    corrected to Hyper-V Ubuntu VM + Docker Engine.
- **Decisions:** all 4 research addition packs adopted (compliance, ops/
  quality, training/rollout, platform services); **one shared core workflow
  engine** (built at R-4, supersedes module-internal approach); React shell +
  component library land with R-2; Wave-2 order A→B→C (swappable); Risk
  Registry + Management Review grouped into QMS module; remaining open
  decisions in master plan §4.
- **Docs updated:** master-plan.md (new), docs/research/ (new, 19 files),
  4 new + 7 updated module docs, 3 standards docs, docs/README.md, CLAUDE.md,
  CHANGELOG.md, this file.
- **Next Session Prompt (archived):** Stage A Increment 2 (ops, revised) —
  full text in the top block as of this session.

### Session 2 — 2026-07-22 — Standards codified + Phase 0 Increment 1 ✅

- **Phase(s):** 0 · **Commits:** `0d5a18c` (baseline) → `f0b39ac` (docs) →
  `b6e689b` (Increment 1) → `f76dd9b` (review hardening) — all **local**
  (push waits for the Phase 0 gate; no remote yet)
- **Done:**
  - 9 standing dev rules codified: `CLAUDE.md` session contract,
    `docs/standards/` (development-workflow, database-standards, ui-standards,
    tech-stack), `docs/modules/` (foundation + reimbursement real content,
    5 scaffolds), PROGRESS restructure, CHANGELOG, docs index.
  - Phase 0 Increment 1: `app/` → `office_connect/` restructure;
    Base + naming convention + Audit/SoftDelete/Lookup mixins; `core/time.py`;
    Alembic async chain + migration 0001 (5 spine tables, `oc_app`
    least-privilege role, seeds); automatic hash-chained audit trail;
    global soft-delete filter; `GET /api/v1/config` fail-safe OFF;
    31 QA-gate tests; import-linter contracts.
  - 34-agent adversarial review → 23 confirmed findings fixed (float/jsonb
    hash asymmetry, cascade/bulk-DML audit bypasses, cache poisoning,
    password dollar-quoting, test isolation, and more).
- **Verified:** from a **wiped volume**: `alembic upgrade head` ×2 idempotent,
  downgrade→re-upgrade clean, **pytest 31/31**, `lint-imports` 2/2 kept,
  `/health` healthy, `/api/v1/config` all flags OFF, Laragon untouched.
- **Decisions:** see `docs/modules/foundation.md` §7 (naming plural, BIGINT
  PKs, app-level audit listeners, no delete-orphan/bulk DML, `.devN`
  versioning, accepted limits).
- **Docs updated:** CLAUDE.md, all 4 standards docs, all 7 module docs,
  docs/README.md, README.md, CHANGELOG.md, this file.
- **Next Session Prompt (archived):** Phase 0 Increment 2 (ops: deploy guard
  script, backup + proven restore, Celery worker, migration-on-boot, git
  remote provisioning) — full text in the top block as of this session.

### Session 1 — 2026-07-22 — Dev environment set up & verified ✅

**Milestone: local development environment running and proven to coexist with
the existing Laragon `dev_pims` app on the same machine.**

- **Phase(s):** 0 (pre-work) · **Commit:** `0d5a18c` (local — committed at start of session 2)
- **Done:**
  - Project scaffold: `docker-compose.yml` (`postgres:16` + `redis:7` + FastAPI
    `app`), `Dockerfile` (python:3.12), `requirements.txt`, `app/main.py`
    (`/` + `/health` pinging Postgres & Redis), `app/core/config.py`,
    `app/core/db.py` (async SQLAlchemy pool 10/20), `.env`/`.env.example`,
    `scripts/setup-windows.ps1`, `scripts/smoke-test.ps1`, `README.md`, git init.
  - Docker Desktop + WSL2 installed (elevated), engine running (server 29.6.2).
- **Verified:**
  - Stack builds and starts: `db` healthy, `redis` healthy, `app` up.
  - `http://localhost:8001/health` → **200**
    `{"status":"healthy","checks":{"postgres":"ok","redis":"ok"}}`
  - Runs simultaneously with Laragon `dev_pims`, zero conflict — Laragon owns
    80/3306/8000, Office-Connect owns 8001/5432/6380.
- **Decisions:**
  - Production host = **on-prem Windows Server** (after development), NOT
    Hugging Face; CSS-IS stays on HF and is migrated in
    (`references/Hosting_Target_Clarification.md`, overrides plan C-4).
  - First user-facing module = **Local Travel Reimbursement**
    (`references/Phased_Rollout_Assessment.md` §0.1).
- **Next Session Prompt (archived):** *"planning and creating skills continue
  next session"* — Phase 0 foundation build (Alembic chain, `core_*` spine,
  hash-chained audit, `/api/v1/config` fail-safe OFF, package restructure,
  pytest QA gates).

---

## How to run

```powershell
docker compose up -d        # start (add --build after changing deps/Dockerfile)
docker compose ps           # status
docker compose logs -f app  # API log
docker compose down         # stop (Laragon unaffected)
```
Open: http://localhost:8001/health · http://localhost:8001/docs
