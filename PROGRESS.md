# Office-Connect — Progress Tracker

## ▶ RESUME *(copy this one line to start the next session)*

> **Resume Office-Connect — Stage C R-6-liq: the liquidation workflow + settlement (the A/B/C certification chain, LQ- numbers, GAM App 44, refund-OR and the over-advance spawn).**

That one line is all you paste. Per the start-of-session ritual I read the
*Current Status* + *Next Session Prompt* below (and the cited module docs) to
expand it into the full task and confirm with you before starting.

## ▶ CURRENT STATUS *(overwrite each session)*

- **Phase:** **Stage C IN PROGRESS** — **R-1 ✅ + R-2 ✅ + R-3 ✅ + R-4 ✅ +
  R-5 ✅ (gen + packet) + R-6-clock ✅**. **The module now has both halves of a
  travel claim's money story: what is owed, and what is owed BACK.** A cash
  advance is recorded by Accounting, its COA 30-day deadline is computed and
  **pinned**, a countdown ring shows it on My-Work / the register / the claim
  rail, and a daily ladder warns the traveller at **D-7 / D-3 / D-0 / overdue**
  (email at D-3 and D-0 per spec §12) before flipping the advance to `overdue`.
  `deadline_check` is **live** after three sessions registered-but-inert.
  **Migration head `0019`** (`deadline_date` + `deadline_basis`, backfilled).
  **Verified: pytest 737 passed (+79) with ZERO failures** — the SLA-ladder test
  that had failed since session 18 is fixed, not skipped — plus lint-imports
  3/3, `alembic check` clean, `0019` reversible, seeds ×2 no-op, FE gate green
  (tsc + eslint + **168 vitest**, +18, + build), and a live smoke through the
  **real Celery worker** (pinned clock, §89 409, the whole D-ladder, idempotent
  re-beats, authenticated HTTP round-trip).
  **`module.reimbursement` is ON in dev.** Prod default stays OFF.
  **NOT pushed** — push cadence: **once at the Stage C QA gate**.
- **Last session:** #21 — 2026-08-04 — **Stage C R-6-clock: cash advances + the
  COA 30-day liquidation clock**. R-6 split into **R-6-clock / R-6-liq** (the
  fourth such split, after R-2/R-4/R-5) because the briefed scope was roughly
  double any prior increment. **R-0 item 1 is CLOSED**: calendar days per COA
  97-002, with `basis` honoured as a **live config switch** so confirming DOH
  working-day practice later is a config edit rather than a code change plus a
  data migration — and the guess would have mattered, because the same "30 days"
  is **12 calendar days apart** between the two bases. Built:
  `services/deadline.py` (pure), `services/cash_advance.py` (the single
  sanctioned writer), migration `0019`, `reimb.cash_advance.manage` +
  the `liquidation.overdue_note` seed, four routes on the gated router with a
  **server-derived** countdown, the `deadlines` fact (`FACTS_VERSION` → 2),
  `sweep_liquidation_reminders` + `ops.reimb_liquidation_reminders` (daily 08:35
  Manila), `CashAdvanceOut` on `ClaimDetail`, and FE: **CountdownRing**
  (inventory row 22), the CA card, the Accounting register, the My-Work section
  and the claim rail.
- **⚠→✅ THE 3-SESSION-OLD FAILURE IS FIXED, AND IT WAS THE SESSION-17
  PRODUCTION DEFECT ALL ALONG.** `sweep_sla_reminders` budgeted its work-list as
  `ORDER BY WorkflowStep.id ASC LIMIT 200` — a budget that always starts at the
  same end of the queue, so once ~200 steps are permanently stuck, every
  newly-overdue item sits behind them **forever** (spec §7.5 inverted). It
  surfaced as a test failure at **session 18** purely because that is the session
  that added 146 tests and pushed the suite's accumulated backlog past 200; the
  dev DB held **450** such steps when measured. Fixed by ordering
  most-overdue-first **and draining in keyset pages** — ordering alone fixes the
  priority but not the starvation, because the newest overdue item is by
  definition the *least* overdue. Truncation is now logged, never silent. Two
  regression tests pin it; the new liquidation ladder was written drained from
  the start rather than inheriting the shape.
- **Decisions this session** (four user-confirmed at kickoff): **calendar days
  with `basis` as a live switch**; **split R-6-clock / R-6-liq**; **Accounting
  records a cash advance** (new `reimb.cash_advance.manage`; `dv_no`/`dv_date`
  are data only Accounting holds, and the PD 1445 §89 block is only worth having
  if the record it guards is authoritative); and **fix both SLA-ladder problems
  here**, because R-6 owns the clocks and going green before adding a second
  ladder on the same machinery was the cheapest it would ever be.
- **Design notes worth remembering:** the deadline is **PINNED, not derived** —
  the sweep's range query and the `liquidation_deadline` precedent are the
  practical reasons, but the decisive one is that a date a traveller was *told*
  must not silently move when an admin edits a config row; recomputed on exactly
  one trigger (`date_return`), the R-5-gen `purpose` lesson applied to a clock.
  **Compliance clocks fail SHORT** — the opposite direction to the checklist
  grammar's fail-OPEN for an unparseable rule, because a rule failing open leaves
  a visible flag someone can action while a deadline failing open quietly grants
  time that does not exist. **PD 1445 §89 became a sentence**: the hard-block has
  been a DB index since R-1, which meant an Admin Officer hitting it got a 500.
  **Milestones are "most urgent threshold REACHED"**, so a missed beat still
  warns — at the level that is now true, never a stale "7 days left". The dedup
  key carries the **channel**, because D-3/D-0 send twice and without it the
  email would silently dedup away against the in-app row.
- **Two findings, neither introduced here:** **`created_by`/`updated_by` are NULL
  platform-wide** (0 of ~1,450 live `reimb_claims`) — the ownership columns exist
  on every business table and nothing populates them, so standing rule 5 rests
  entirely on the hash-chained `core_audit_logs` trail today. Recorded, not
  widened into this increment: it is a foundation change touching every table.
  And **`FormDialog` now sets `noValidate`** — native constraint validation was
  BLOCKING the submit event on an empty required field, so react-hook-form never
  ran and the user saw a browser bubble instead of the GOV.UK error that
  ui-standards §3.14 requires to match the server's wording.
- **Test-hygiene note:** a full-suite run can leave `module.reimbursement` OFF in
  dev — `test_reimb_api_flag_gate.py`'s `reimb_flag_off` fixture restores
  whatever state it captured, so an interleaved run can persist the OFF. Flip it
  back with `python -m office_connect.ops.bootstrap set-flag module.reimbursement --on`.
- **Blockers / waiting on user:** none.
- **⚠ Open questions for the accountant / resident COA auditor (unchanged, not
  coding decisions):** the **A/B/C certification chain + wet-sign capture** (R-6-liq
  needs it), and whether **CTC-47** ("Certificate of Travel Completed", seeded
  `claim_kind='reimbursement'`, `{"always": true}`, `external_wet_sign`) belongs
  on reimbursement at all — it is signed *after* the trip and reads like a
  liquidation artifact. Built as seeded (spec-faithful); re-scoping it is a
  policy call, best taken when R-6-liq authors the liquidation catalog.

## ▶ NEXT SESSION PROMPT *(rule 3 — the full brief I expand the RESUME line into)*

```text
Context: Stage A + Stage B complete/pushed. Stage C IN PROGRESS - DONE: the shared core
workflow engine (#11), R-1 (#12), R-2-engine (#13), R-2-shell (#14), R-4-app (#15),
R-2-wizard (#16), R-4-screens (#17), R-3 (#18), R-5-gen (#19), R-5-packet (#20) and
R-6-clock (#21). R-6 was SPLIT: R-6-clock shipped the cash-advance record, the pinned
COA 30-day deadline, the D-7/D-3/D-0/overdue ladder, the countdown UI and the live
deadline_check. R-0 item 1 is CLOSED (calendar days; `basis` is a live config switch).
The suite is at 737 passed with ZERO failures - the SLA-ladder failure that stood from
session 18 was the session-17 LIMIT-200 starvation defect and is fixed.
Task: Stage C R-6-liq - THE LIQUIDATION WORKFLOW + SETTLEMENT (spec 6.2, 5.5, 8
settlement, 9.2 liquidation tracker, 10, 14 R-6). The clock exists; now build what
answers it.
Build: the `reimbursement.liquidation` workflow definition as a SECOND definition on
the shared engine (rule 10 + the R-4-app precedent - definitions are DATA, NOT new
tables). Spec 6.2 reads `CA Open -> Liquidation Draft -> Submitted -> Certifications
(A->B->C in order) -> Handed to FMS -> ... -> Settled`; per the R-4-app decision
A = claimant IS THE MAKER and is folded into submit, never a checker slot, so the
authored chain is draft -> certify_b (Director IV) -> certify_c (Head, Accounting Unit,
external wet-sign captured by the Admin Officer) -> handed_to_fms -> settled, plus the
returned loop + cancelled. NOTE two things that MUST be generalized first:
`workflow.py::_assert_graph_invariants` asserts authored states == services.status
ALL_STATES (claim-only today), and services/status.py's CLAIMANT_STATES /
EXTERNAL_STATES / NEXT_ACTION are read by lifecycle.resolve_holder and
_sync_claim_from_event - both need to become kind-aware, not forked.
Also: LQ-YYYY-NNNN via core-service #5 (allocate_reference_number, scope="LQ" - do NOT
rebuild); the liquidation checklist catalog rows (claim_kind='liquidation' is already
legal and services/checklist.py is already kind-aware) INCLUDING the first seeded
`deadline_check` (its substrate shipped at R-6-clock: facts["deadlines"] is populated
from the linked advance, keyed "liquidation.deadline"); GAM App 44 Liquidation Report
as a fifth DocumentSpec + a `_lr44_body.html.j2` partial + a reimb_template_maps row
with claim_kind='liquidation' (the packet machinery is built - add a template and a
binding, and register the partial in registry.BODY_PARTIALS); settlement recording -
services/per_diem.py::settle ALREADY computes (to_reimburse, to_refund), so what is
missing is the RECORDING: the refund side-step captures the DOH OR no./date and settles
the advance (cash_advance.mark_settled), and the over-advance side spawns a linked
pre-filled reimbursement claim of the difference (needs a claim<->claim link column -
migration 0020); the spec 9.2 liquidation tracker screen ("same as claim tracker +
30-day countdown ring" - CountdownRing is inventory row 22 and ships).
OPEN WITH THE RESIDENT COA AUDITOR - blocking for the chain: (1) confirm the A/B/C
certification chain and that external wet-sign capture (Admin Officer uploads the signed
page and checks the step) is acceptable for certification C - they are FMS, outside the
platform; (2) whether CTC-47 belongs on reimbursement at all or is a liquidation
artifact - it is seeded always-on `external_wet_sign` on reimbursement today and reads
like a liquidation document. Best answered now, while the liquidation catalog is being
authored. Signature CAPTURE was deferred FROM R-5 to here (module-doc row 98) - the
snapshot half of core-service #3 is built and is everything a signature binds to
(frozen bytes, both hashes, signer identity, timestamp, void-on-edit, stale_snapshots()).
Available to build on - do NOT rebuild any of it:
CORE - the workflow engine (#11), reference numbers (#5), checklist engine (#7),
documents (#8) + snapshots (#3), attachments (#2), notifications outbox + the enqueuer
seam, core/workdays.py.
MODULE - services/lifecycle.py is the ONLY sanctioned caller of start_instance/
execute_action (workflow-standards 1); services/cash_advance.py is the ONLY writer of
reimb_cash_advances and already exposes mark_liquidation_started / mark_settled /
link_claim / open_cash_advance_for; services/deadline.py is the pure clock;
documents/registry.py + the _*_body.html.j2 partials show how a form is added;
notify.py shows the drained-page sweep shape BOTH ladders now use - copy that, never a
single LIMIT.
Migration head 0019 - R-6-liq WILL need 0020 (the spawned-claim link + any refund-OR
columns).
pytest 737 (0 failures), lint-imports 3/3, FE gate green (168). Dev flag ON - but a full
suite run can leave it OFF; `python -m office_connect.ops.bootstrap set-flag
module.reimbursement --on` restores it.
Push cadence: once at the Stage C QA gate.
Read CLAUDE.md, then docs/modules/reimbursement.md (delta register - the R-6-clock rows
and section 3's R-0 tracker), docs/standards/workflow-standards.md (authoring a second
definition), master-plan 1.1 #3/#5/#7/#8, api-standards 9/9a/9b/9c/9d/9e, ui-standards
3+4, and spec 5.5, 6.2, 8 (settlement), 9.2 liquidation tracker, 10 and 14's R-6 row.
Rule 10 throughout; everything auditable + soft-deleted; money server-computed.
```

## Stage tracker *(rule 4 — commit per session, push per phase/stage gate)*

Stages per `docs/master-plan.md` §2 (old phase numbers kept for traceability).

| Stage | Old # | Scope | Status | Sessions | QA gate | Pushed (tag / date) |
|---|---|---|---|---|---|---|
| A | 0 (inc 1–4) | Foundation: spine ✅, ops ✅, integrations ✅, spine amendments ✅ | complete (pushed) | 1–6 | ✅ passed | `phase-0-complete` / 2026-07-23 |
| B | 2 | Identity & access: auth / RBAC / directory / delegation | complete (pushed) | 7–10 | ✅ passed | `phase-2-complete` / 2026-07-27 |
| C | R-0…R-9 | Reimbursement vertical + core workflow engine + first React shell | in progress (R-1 ✅ + R-2 ✅ engine/shell/wizard + **R-3 ✅** + **R-4 ✅** engine core/app/screens + **R-5 ✅** gen/packet + **R-6-clock ✅**) | 11–21 | — | — |
| D | 3 | Landing shell / query bar / Calendar surface / AI service | not started | — | — | — |
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
