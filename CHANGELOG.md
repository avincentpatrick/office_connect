# Changelog

All notable, user-visible changes to Office-Connect. Format follows
[Keep a Changelog](https://keepachangelog.com/); versions align to **phase
completions** (e.g. `0.1.0` = Phase 0 complete) and match the `APP_VERSION`
constant in `office_connect/__init__.py`.

`[Unreleased]` accrues session by session and is promoted to a version at each
phase QA gate (see `docs/standards/development-workflow.md` §6) — this is what
makes the push-per-phase rule auditable.

## [Unreleased]

### Added
- **Stage C R-5-packet — one packet you can print and hand over** (2026-08-04):
  the three generated forms stop being three separate downloads. Office-Connect
  now builds a **single printable packet** for every claim: a **cover sheet**
  carrying the reference number, claimant, purpose, travel dates and the amount
  due; the **COA checklist** as a final-check sheet showing what is required and
  what is done; a **manifest of your supporting documents**; and then the
  Itinerary, the accomplishment report and the Disbursement Voucher **in full**.
  Six pages, A4, print-faithful — an Admin Officer can print it once and walk it
  to Accounting instead of assembling three PDFs by hand in the right order.
  **The manifest lists your receipts; it does not reprint them.** COA takes the
  original documents, so the packet's job is to say exactly what must travel with
  it — every file is listed with its checklist code, its size and a **SHA-256
  fingerprint**, so a receipt in the envelope can be matched to the copy on file
  years later. A file that failed its virus scan is shown as quarantined rather
  than quietly left off the list.
  **Approvers now see what they are approving.** `/claims/:id` gains a **Packet**
  card: the PDF is embedded on a desktop screen and is one tap away as
  "Open the packet" on a phone, right above the Approve / Return bar. Claimants
  see the same card on Review (clearly marked **Draft copy** — no reference
  number yet) and on the confirmation page once the claim is filed.
  **It stays honest about itself.** Attach or remove a receipt and the packet is
  withdrawn rather than left describing documents you no longer have; the cover
  prints the fingerprint of the exact data it was built from. If the background
  service is down, the card says so plainly and the approve/return decision is
  never blocked — and an approver told to "print the packet" can now ask for one
  themselves rather than waiting on the claimant.
  Verified: **pytest 658 (+9) on a migrated database, lint-imports 3/3, no new
  migration (head stays `0018`), FE gate green (150 tests, +10)**, and a live
  smoke through the real background worker and real PDF engine: a **6-page
  packet**, evidence attached → packet withdrawn → regenerated → the new receipt
  on the manifest.

- **Stage C R-5-gen — the system writes your paperwork** (2026-08-04): the
  module's founding promise, finally kept. Enter your trip once and Office-Connect
  fills in the **Itinerary of Travel (GAM Appendix 45)**, your **accomplishment
  report** and the **Disbursement Voucher (GAM Appendix 32)** — no re-typing the
  same dates, places and amounts across three forms. On the Documents step those
  three items stop saying "nothing for you to do" and become **Generated cards
  with a preview link** that opens the real PDF in a new tab, so you can read what
  will be filed in your name before you file it. The documents are A4,
  print-faithful, and carry your reference number and the Manila time they were
  prepared on **every page** — a page separated from its packet still says what it
  is. Every figure on them is the number the server computed; nothing is
  recalculated at print time, so the voucher can never disagree with the claim.
  **Nothing is ever silently out of date.** Before you submit you get a clearly
  watermarked **DRAFT** (it has no reference number yet, and says so). Change
  anything on the claim and the prepared documents are withdrawn rather than left
  sitting there describing a trip you have edited. When you submit, the packet is
  regenerated as the filed original, stamped with your `RB-` number, and the draft
  is retired — with every earlier version kept, so an auditor can always see what
  was issued and when. **Preparing your documents can never cost you a submission.**
  It runs in the background; if the service is briefly unavailable you get a plain
  notice, your claim is still saved, and you can still submit — generated documents
  never block the submit check, because they are produced downstream of it.
  Verified: **pytest 649 (+34) on a clean database, lint-imports 3/3, migration
  `0018` reversible, FE gate green (140 tests, +3)**, and a **23-check live smoke**
  driving the whole chain through the real background worker and real PDF engine:
  generate → preview inline → edit → packet withdrawn → submit → filed original.

- **Stage C R-3 — the checklist decides what a complete claim is** (2026-08-03):
  the wizard gains a fifth step, **Documents**, and it is the packet screen the
  whole module was built around. Your required documents are generated from the
  COA checklist **and from your own claim**: pick taxi on a leg and the
  reimbursement expense receipt appears; enter other expenses and the lodging
  receipt appears; a job-order claimant is asked for the head-of-office
  certification and nobody else is. Each one says why it applies, in plain
  language. Upload a scan or a photo — drag it in, or take it with your phone
  camera — and the item ticks over, with an always-visible line telling you where
  you are ("2 of 3 required items done"). **A claim can no longer be submitted
  with a required document missing.** Submit names exactly what is absent and
  links you straight to it, and a refused submit costs you nothing: no reference
  number is burned and nothing enters the approval chain. Files are checked for
  viruses in the background; yours counts towards the packet the moment it is
  saved, and we say so rather than pretending it is ready to open. **Approvers
  now see the automatic checks.** A fare over the ₱300 no-receipt limit raises an
  amber callout above the decision buttons, with the reason spelled out — you can
  still approve, and the confirmation says plainly that approving past a flag is
  recorded against your name. You can never approve past a *missing* document:
  the button is withheld and a red callout explains why, with **Return** always
  available. Claim files are readable only by people who may read that claim, and
  are filed under the 10-year records-retention class. Verified: **pytest 616
  (+146) on a clean database, lint-imports 3/3, migration `0017` reversible, FE
  gate green (137 tests, +41)**, and a 19-check live smoke driving the whole
  journey — refused submit, upload, submit, holder-scoped download, approve past
  a flag.
- **Stage C R-4-screens — approvers can now clear their queue, from a phone**
  (2026-08-03): the other half of the claim's life. A claim waiting on you shows
  **Approve** and **Return** on the claim page itself, pinned to the bottom of the
  screen on a phone so you never scroll back to act. The buttons come **entirely from
  the server** — the same page shows a claimant nothing, and it will not offer you
  Approve on a claim you filed yourself, because you can never clear your own claim
  even as the Division Chief. One Approve carries the claim all the way down the
  chain, and the button says what it will actually do at each step: *Approve*, then
  *Approve & hand to FMS*, then *Mark paid & close*. **Returning now requires at
  least one reason** picked from the published taxonomy plus a comment — the dialog
  stays open and keeps your work if either is missing, and the claimant sees both
  **word for word**. Every claim page carries a **tracker**: who did what, when
  (Manila time), and the reasons attached to the bounce that produced them. **My
  Work** rows now carry an urgency chip — amber when an approval is due soon, red
  when it is overdue — computed from the step's own deadline. If two people act at
  once, the second is told the claim moved rather than silently overwriting the
  first. And switching the module off no longer traps work in progress: new claims
  stop, but a claim already in the chain can always be finished. Verified: **pytest
  470 (+28), lint-imports 3/3, FE gate green (96 tests, +21)**, no migration (schema
  unchanged), live end-to-end smoke driving a claim from filing to *Paid / Closed*.
- **Stage C R-2-wizard — file a travel claim end to end** (2026-07-30): the
  reimbursement module opened its first screens and API. From **My Work** (the module
  landing: "Waiting on you" above "Your claims in flight", each row with holder,
  days-in-state, and the next action) a claimant starts a claim and walks a GOV.UK-style
  **4-step wizard** — Trip → Itinerary → Money → Review & submit — with the task-list
  sidebar always showing progress. **Every Continue saves to the server**, so you can
  leave and resume any time from the task list (a returned claim re-opens fully
  editable); claimant identity (name, position, division, JO/COS status) is prefilled
  from the directory and never re-typed. The money step sends your inputs and the
  **server computes every total** (EO 77 per-diem breakdown by day, transport, other
  expenses) — the browser never does money math. Check-your-answers shows the whole
  packet with per-row Change links; submitting is the real atomic submit and lands on a
  confirmation page with your permanent **RB- reference**. New other-expenses field is
  now remembered across returns/resubmits (migration `0016` fixed a latent reset-to-zero
  bug). Claims are **not bureau-public**: reads are owner-or-scoped (your chief sees the
  division, the Admin Officer the office). The whole surface sits behind the
  `module.reimbursement` flag (OFF = indistinguishable from absent; a new audited
  `bootstrap set-flag` command flips dev on). UI inventory grew to 17 components
  (Select/Textarea/Checkbox/RadioGroup fields, Summary list, Confirmation panel,
  Work-item row) — form validation via react-hook-form + zod, shape-only, with GOV.UK
  error summaries. Verified: **pytest 442 (+29), lint-imports 3/3, FE gate green (75
  tests)**, migration `0016` reversible, live end-to-end smoke through :5174.
- **Stage C R-4-app — claims now run on the approval workflow** (2026-07-29): the
  reimbursement chain is live on the shared engine as its first real definition
  (`reimbursement.claim`: Division Chief approve → Admin Officer review → hand to FMS →
  Paid/Closed, with return loops and owner cancellation; no reject — returns are the
  spec's only loop-back). **Submitting a claim is now one atomic action**: the server
  computes the money, allocates the permanent `RB-YYYY-NNNN` reference, starts the
  workflow, and stamps status/holder/next-action — a claim always shows exactly one
  holder and one plain-language next step (work-management non-negotiables), and every
  move lands in the append-only status history. Approvals enforce segregation of duties
  (you can never clear your own claim, even as the Division Chief) and org scoping (a
  chief approves only their own division). SLA: each human gate is due in 3 WORKING
  days (Manila calendar, holidays honored); the overdue holder gets one nudge and then
  a repeat every 2 working days — **to the holder only, never superiors** — all
  idempotent. New `admin_officer` role + `reimb.claim.review`/`reimb.claim.fms_update`
  permissions; new bootstrap `seed-workflows` step and `load-reference` now installs
  the module's reference data too. Migration `0015` (one live workflow instance per
  claim, DB-enforced). The `module.reimbursement` flag stays OFF (fail-safe) — flag ON
  blocks nothing in-flight, only new submissions. Verified: **pytest 413 (+36),
  lint-imports 3/3**, migration `0015` reversible, seeders re-run as no-ops.
- **Stage C R-2-shell — the first React frontend** (2026-07-28): Office-Connect now has a
  user interface. A `web/` Vite SPA (React 19 + Tailwind 4 + TypeScript, exact-pinned;
  Node 22 LTS) served by a new compose **`web` service on :5174** that proxies `/api` to
  the backend same-origin (no CORS). Ships the **app shell** (top bar, `NAV_GROUPS`
  navigation gated by feature flags + roles, notification bell, skip-link), all **6 layout
  templates**, and the **14-component inventory seed** (Button, Form field, Card, Tabs,
  Status chip, GOV.UK Task list, Stepper, Timeline, Pipeline card, Dialog, Empty state,
  Skeleton, Toast/bell, GOV.UK Error summary — a new inventory amendment) — all styled
  exclusively from the tenant design tokens served by `/api/v1/config`, injected at
  runtime so tenant re-branding needs **no rebuild**. Full sign-in flows work end to end:
  login → forced password change → forced MFA enrollment (the bootstrap-admin day-one
  path), session-expiry redirect, rate-limit countdown, actionable GOV.UK-style error
  summaries. Reimbursement appears as a flag-gated placeholder list (`module.reimbursement`
  stays OFF); a DEV-only `/ui-foundation` catalog renders every component. **No backend
  changes** (migration head stays `0014`). New FE dependency set recorded in
  tech-stack §4; ui-standards §7/§8 filled. Verified: FE gate green (eslint + tsc +
  vitest 28 + build), pytest **377 unchanged**, lint-imports 3/3, live proxy smoke
  (config 200 / CSRF 403).
- **Stage C R-2-engine — the per-diem computation engine** (2026-07-27): a claim's
  money is now computed **server-side** from its itinerary + the seeded EO 77 rules — a
  per-day breakdown (100% arrival/full days, 50% departure/return day and same-day trips,
  host-provided lodging/meals strips, government-vehicle fare suppression, and the 50-km
  rule: within 50 km without an overnight stay pays transport fare only) rated per day at
  that day's destination cluster and effective-dated rate. Writes each leg's
  `per_diem_pct/per_diem_amount/leg_total` and the claim's `totals` snapshot
  (`{per_diem, transport, other, grand, advance, to_reimburse, to_refund, days[]}`), with
  cash-advance settlement (refund due vs "Reimbursement Due"). Two new claimant
  attestations on the claim (`is_within_50km`, `overnight_stay`, migration `0014`).
  Establishes the **platform money convention** (`core/money.py`): `ROUND_HALF_UP` to the
  centavo, quantize-components-then-sum, money-in-JSONB as 2-dp strings
  (database-standards §10). The spec §8 worked example (**₱5,500**, 3-day Manila trip) is
  the pinned QA anchor. Verified: **pytest 377 (+37), lint-imports 3/3**, migration
  `0013↔0014` reversible. No new dependency.
- **Stage C R-1 — Local Travel Reimbursement schema + config pack** (`reimb_*`,
  2026-07-27): the reimbursement data model on top of the workflow engine — 13 `reimb_*`
  tables (migration `0013`): the claim header (`reimb_claims`, with `workflow_instance_id`
  FKing INTO the shared engine) + itinerary legs, cash advances, the effective-dated EO 77
  3-cluster DTE rate tables (`reimb_dte_clusters` + a PSGC `reimb_region_clusters` map,
  replacing the old 2-tier per diem), the config pack (`reimb_configs`, with legal sources),
  the documentary-requirements catalog + per-claim items, the return-reason taxonomy +
  append-only return/status/external-event logs, and the core-attachments join. The
  **cash-advance hard-block** (PD 1445 §89 — at most one unliquidated CA per claimant) is a
  DB constraint. Ships the **core reference-number service** (`RB-`/`LQ-YYYY-NNNN`, yearly
  reset, never reused) that every module will use. Regulatory reference data (EO 77 clusters,
  PSGC region map, COA-2023-004 checklist, return reasons, config) is seeded. Computation,
  the wizard, and the approval-definition wiring come in R-2/R-4-app. Verified: **pytest 340
  (+20), lint-imports 3/3**, migration `0013` idempotent + reversible. No new dependency.
- **Stage C — the shared core workflow engine** (`core_workflow_*`, 2026-07-27): the
  ONE approval/routing engine every module will consume (Rule 10 + master-plan §1.1 #1),
  built as a pure core service ahead of its first consumer (reimbursement R-4). A workflow
  is authored as versioned, **immutable-once-published** definitions (states + transitions
  with **typed** amount/permission guards — no DSL), started as an instance pinned to its
  version, and driven by an atomic, idempotent, compare-and-swap `execute_action`
  (409 on a stale version or a lost race). Approval gates route by org scope
  (`authorize_scoped`) + segregation-of-duties (no self-approval, distinct four-eyes
  approvers), with **delegation / OIC** recorded as "acted on behalf of". The
  append-only, **audited** event log is the authoritative history — the instance's current
  state is a derived read-model proven by an event-fold consistency check. Return loops
  back (resubmit restarts, revision-tracked); reject is terminal. An idempotent,
  non-interrupting SLA sweep (`ops.sweep_workflow_sla`, beat every 5 min) escalates overdue
  steps to the holder only. A module's feature flag blocks **new** instances while in-flight
  ones always finish. New permission strings `workflow.definition.read/manage/publish`,
  `workflow.instance.read`, `workflow.delegation.manage` (auditor gets the reads). Contract:
  `docs/standards/workflow-standards.md`. Verified: **pytest 320 (+34), lint-imports 3/3**,
  migration `0012` (8 tables + 6 enums; `core_workflow_events` append-only + REVOKE UPDATE;
  idempotent + reversible). No new dependency.

## [0.2.0] — 2026-07-27 — Phase 2 (Stage B) complete

### Added
- **Stage B (Phase 2) Increment 4 — wire seams + directory + compliance**
  (2026-07-27): closed the deferred shared-service seams and the Stage-B compliance
  gates. **Authed attachments HTTP router** (`/api/v1/attachments`) — upload
  (magic-byte validated, size-capped, `pending`), streaming auth-checked download
  (serves the EXIF-stripped derivative), metadata, soft-delete, disposal report —
  each gated by an `attachment.*` permission string, with a **per-upload malware-scan
  enqueue after commit** (the beat sweeper remains the backstop) and a holder-scoping
  authorize seam ready for Stage C. **Notification recipient/preference resolution** —
  a `recipient_user_id` now resolves to the login's email (staff-email fallback), and
  a new `core_notification_preferences` opt-out table suppresses opted-out
  channel/module deliveries (persisted as `suppressed`, never dispatched) while
  **security/transactional** notifications always send. **CSS-IS directory
  ingestion** — a pure, idempotent, atomically-validated upsert of a CSV org/staff
  feed into `core_org_units`/`core_staff` (topological tree insert, tombstone restore,
  leave-alone by default), exposed as `POST /api/v1/directory/import` and a
  `bootstrap ingest-directory` CLI, now the single code path `load-fixtures` uses.
  **Admin user provisioning** (`/api/v1/users`) — create a login from a staff record
  (temporary password, forced change; **no self-registration**), deactivate (revokes
  every Redis session immediately) / reactivate, all hash-chained; role grants and
  password reset reuse the existing RBAC/auth endpoints. **Query-log middleware** —
  one append-only `core_query_logs` row per `/api/v1` request (ids + param names +
  status only, never bodies/values/SPI), the COA read-access posture. **Full
  person-field SPI redaction** — `core_staff` name/email and notification
  recipient/body/payload VALUES are withheld from the immutable audit chain (field
  names kept; the live row is the source of truth), extending the B1 credential
  subset. **Stage-B PIA** + processing-register row (NPC Advisory 2017-03). Adds
  `python-multipart`. Verified: **pytest 286 (+48), lint-imports 3/3**, migration
  `0011` (notification preferences + `suppressed` status; idempotent + reversible).
- **Stage B (Phase 2) Increment 3 — RBAC enforcement** (2026-07-23): real
  authorization on the B2 auth runtime (**no migration**). **Permission-gated
  routes** — every protected endpoint declares a permission *string* (never a role
  name); `require_permission(perm, scope=)` resolves the actor's effective set from
  a **Redis cache** (db 4) keyed by `core_users.permissions_version`, so a cache hit
  takes no DB hit. **Grant/revoke lands on the next request** — an admin grant/revoke
  bumps the version and stamps it onto the target's live sessions, taking effect
  immediately without a re-login; no pub/sub. **Org-unit-scoped authorization** —
  `scope=REQUESTER` checks the actor's grant against the request's org unit by
  walking the `core_org_units` ancestry (a scoped `org_unit_id` covers its subtree;
  a global grant covers everywhere). **Delegation / OIC** — time-boxed grants via
  `core_user_roles.valid_from`/`valid_to`, with the cache TTL capped at the next
  window edge so an expiring delegation drops precisely. **Maker-checker** — a
  reusable no-self-approval / distinct-approver segregation-of-duties check (COA
  92-389, NGICS). **RBAC admin API** (`/api/v1/rbac/*`) — grant/revoke roles
  (org-scoped and/or time-bounded) + read the role/permission catalog, emitting
  `rbac.role.granted`/`revoked` hash-chain events. **Read-only auditor** (COA Res.
  2020-034) — `GET /api/v1/audit/verify` renders a printable HTML chain-verification
  report (PASS/FAIL, JSON via `Accept`) and `GET /api/v1/audit/records/{table}/{pk}`
  the per-record timeline; the `auditor` role is read-only everywhere by permission
  gating alone. New error slugs `forbidden` (403) and `segregation_of_duties` (409).
  Verified: **pytest 238 (+25), lint-imports 3/3**, no schema change.
- **Stage B (Phase 2) Increment 2 — authentication** (2026-07-23): the login
  runtime on the B1 identity floor (**no migration**). **Cookie-based server-side
  sessions** on Redis (logical db 4) — an opaque HttpOnly/`SameSite=Lax`/`Path=/api`
  session id, fresh at login and rotated on privilege change; logout destroys the
  server-side record; server-enforced timeouts (12 h absolute; 30 min idle for
  privileged roles / 60 min staff); a concurrent-session cap (3, oldest evicted);
  revoke-all on password change / deactivation; "active sessions" listing + remote
  revoke. **Argon2id login** reusing the B1 hasher, with transparent re-hash on
  cost upgrade. **NIST 800-63B-4 password policy** — min 12, no composition, no
  rotation, and a vendored **top-100k blocklist** (no runtime cloud call).
  **Throttle-not-lockout** — per-account + per-IP backoff after 5 failures with a
  generic, non-enumerating failure. **TOTP MFA** (approver/admin; NPC 2023-06) —
  two-step challenge with enrollment, replay-protected, force-enrollment for
  privileged accounts. **Break-glass** local login (bypasses the future LDAP
  backend). **Custom-header CSRF** on every non-GET. **Auth + CSRF middleware** put
  the real principal on the request so audited writes carry the true `actor_id`;
  logout/session-revoke ride the hash chain via a new `append_auth_event` (no
  secret ever logged). Endpoints under `/api/v1/auth/*` (login, logout, me,
  password change, MFA enroll/confirm/verify, own + admin session management,
  admin password reset) plus the first structured **error envelope**. Adds `pyotp`.
  Verified: **pytest 213 (+58), lint-imports 3/3**, no schema change.
- **Stage B (Phase 2) Increment 1 — identity schema + deferred-FK closure**
  (2026-07-23): the identity floor for "one login". **Split identity model** —
  `core_staff` (plantilla person directory, a superset) + `core_users` (auth
  accounts with a nullable `staff_id` FK). **Org units** — the self-referencing
  `core_org_units` tree (office/division/section/unit) that scopes every approval
  role. **RBAC tables** — `core_roles`, `core_permissions`,
  `core_role_permissions`, and org-unit-scoped `core_user_roles` (grant uniqueness
  uses PG16 `NULLS NOT DISTINCT`; `valid_from`/`valid_to` reserved for B3
  delegation). **Login-attempt log** — append-only `core_login_attempts`
  (anti-enumeration, never stores the password). **Deferred-FK closure** —
  migration `0010` constrains every ownership/actor/org column deferred since
  Phase 0 (`created_by`/`updated_by`/`deleted_by`/`actor_id`/`recipient_user_id`/
  `disposed_by`/`generated_by` → `core_users`, `division_id`/`section_id` →
  `core_org_units`, `tenant_id` → `core_tenant_configs`); the sanctioned
  polymorphic/generic-pointer columns stay unconstrained. **Credential
  redaction** — `password_hash`/`mfa_secret` values never enter the immutable
  audit chain (a `[redacted]` marker keeps the field name; INSERT + UPDATE).
  **Argon2id** password hashing (`core/security/password.py`). **RBAC seeds** —
  idempotent permission (27) + role (4) catalogs and a grant resolver (41 default
  grants) with tombstoned revocations; new `bootstrap seed-rbac` +
  `promote-admin` (break-glass login from the recorded bootstrap admin, temp
  password printed once). Synthetic org-unit + staff dev fixtures (CSS-IS
  decoupled). Migrations `0009`–`0010`. Verified: **pytest 155/155, lint-imports
  3/3**, full chain `0001→0010` idempotent + reversible, FK closure asserted,
  redaction proven, `verify_chain` intact.

## [0.1.0] — 2026-07-23 — Phase 0 (Stage A) complete

### Added
- **Phase 0 Increment 4 — spine amendments** (2026-07-23): the shared "day-1"
  tables and services every later module builds on (Rule 10). **Activity
  taxonomies** — configurable GAD/CCET/DRR/UHC tags as rows (`core_activity_tags`
  + assignments), never boolean columns. **UACS/PREXC codes** — per-FY PAP tree
  (`core_pap_codes`) + 10-digit object codes (`core_object_codes`, travel =
  5-02-01-010-00), effective-dated with UACS never-reuse. **Holiday &
  working-day engine** — `core_holidays` + `core/workdays.py`, the single
  deadline-math engine (weekends + PH holidays/suspensions). **Statutory
  compliance calendar** — the 22 §3.4 deadlines as effective-dated,
  tenant-overridable data (`core_compliance_deadlines`). **Attachments service**
  (`core_attachments`) — magic-byte allowlist → SHA-256 content-addressed store →
  fail-closed malware scan (injectable; ClamAV opt-in via a compose profile) →
  Pillow re-encode/EXIF-strip (HEIC→JPEG); auth-checked streaming downloads
  (service method with an authorization hook; the HTTP router lands with auth in
  Stage B); retention (`retention_class`/`legal_hold`, no auto-purge, disposal
  report). **Notification outbox** — the Increment-3 stub becomes a durable
  outbox + in-app notification-center schema (`core_notifications`) with Celery
  retry + dead-letter (`core_notification_deliveries`); `send_notification`
  signature unchanged. **Report lineage** (`core_report_lineages`) — provenance
  of every generated output. **Seed framework** — idempotent, environment-aware
  reference-data loader (`load-reference`) with named owners + cadences.
  **Observability** — structured JSON logs with request IDs and a fail-safe
  optional self-hosted error tracker (GlitchTip, compose profile); new
  `docs/standards/api-standards.md`. `docs/compliance/` (PIA template, processing
  register, breach runbook, retention schedule) + expanded `docs/operations/`
  runbooks. Migrations `0003`–`0008`. Verified: **pytest 132/132, lint-imports
  3/3**, full chain idempotent + reversible, attachment round-trip incl. EXIF
  strip + fail-closed download, notification dispatch (inline + celery→worker).
- **Phase 0 Increment 3 — integrations + bootstrap** (2026-07-23): the outward-
  facing seams the later modules consume. **Storage driver abstraction**
  (`core/storage/`): a content-addressed interface with a **local-volume driver**
  (the on-prem production default — atomic writes, SHA-256 dedup, bind-mounted
  `./storage`) and a **Google Drive driver** (Shared-Drive-verified). **Email
  driver abstraction** (`core/email/`): **SMTP** (stdlib, the default transport),
  **Gmail API**, and a **log** driver (dev fail-safe that records instead of
  sending), auto-selected by config, behind a **notification outbox stub**
  (`core/notifications/`, core-service #4 seam) with a **test-email path**.
  **Design-token contract**: `GET /api/v1/config` now serves a **`tokens`** object
  — WCAG-AA neutral defaults (palette, 4-px spacing scale, type scale) as the
  single source of truth, with tenant `branding.tokens` overrides merged in;
  present even under the DB fail-safe. **Bootstrap CLI**
  (`python -m office_connect.ops.bootstrap`): `init` (idempotent tenant + flag
  setup), `create-admin` (records the designated System Admin into a **non-public**
  tenant `settings` bag for Stage B to promote — no login yet, no user table
  until Stage B), `load-fixtures` (synthetic dev activities, **refused in
  production**), `send-test-email`. Migration 0002 adds the non-public
  `core_tenant_configs.settings` JSONB (never exposed by `/api/v1/config`).
  Verified end-to-end: local storage round-trips a file (host + container),
  test email sends via the selected driver (logs in dev), bootstrap works and
  refuses fixtures in prod, config serves tokens without leaking the admin;
  **pytest 68/68, lint-imports 3/3**, migration idempotent + reversible.
- **Phase 0 Increment 2 — ops** (2026-07-23): operability + recoverability for
  the foundation floor. Scheduled `pg_dump -Fc` backups (owner role, 3-2-1
  local leg in `./backups`, retention 7) plus a **proven-restore drill** that
  restores into a throwaway scratch database and re-runs the audit-chain
  `verify_chain()` integrity check (seeding a real ≥3-link chain first so the
  check is never vacuously green). **Celery worker + single beat scheduler**
  (Redis transport, broker/results on separate logical DBs) with the nightly
  backup as the first scheduled task. **Migrations as an explicit deploy step**
  (`alembic upgrade head` before app start); the previous migration-on-boot is
  demoted to a dev-only, env-gated (`OC_MIGRATE_ON_BOOT`), advisory-locked
  convenience that production refuses. **Deploy guard** (`--mode dev|release`):
  single-Alembic-head, backup-before-migrate, no-prod-boot-migration, and — at
  release — no `.devN` version and a non-empty CHANGELOG `[Unreleased]`.
  Operations runbooks (`docs/operations/deploy.md`, `backup-restore.md`) and a
  `scripts/deploy.ps1` dev wrapper. Verified end-to-end: wiped-volume deploy
  (explicit + dev-convenience) comes up read-write; drill green; Celery task
  runs via the broker; pytest 31/31; lint-imports 3/3.
- **Master Plan v1** (2026-07-23, `docs/master-plan.md`): authoritative
  consolidation of the reference execution plan + its amending documents +
  two deep-research rounds (18 digests, `docs/research/`) + owner scope
  additions. Build sequence restructured into Stages A–I + Wave 2; binding
  connectedness contract (one shared core workflow engine for every approval
  flow; core-services registry; connection matrix; Rule 10 "shared service
  first"); consolidated statutory-deadline calendar; reference-corrections
  ledger (EO 77 3-cluster travel rates, FOI 15+20-working-day clock, GAM form
  numbering, RA 12009 procurement forms, ₱50k property threshold, and more).
- **Four new planned modules** (owner additions): QMS (controlled documents ·
  risk registry · management review), Supply Management, Planning & Budget
  (WFP/BED/BAR + PPMP/APP), Performance & Deliverables (SPMS · accomplishment
  reports · COA findings) — plus the Calendar of Activities as a connected
  core surface. Module docs scaffolded with government-standard scope.

### Changed
- **DMWIS renamed to DTWIS (Document Tracking & Workflow IS)** to distinguish
  document *tracking* from the new controlled-document *management* module;
  prefix registry updated (`dtwis_`), no schema existed yet.
- Foundation Increment 2 revised (explicit-step migrations replace
  migration-on-boot for production; 3-2-1 backup placement; git remote must
  live off the future production hardware); Increment 4 (spine amendments)
  added. Production substrate corrected to Hyper-V Ubuntu VM + Docker Engine
  in `tech-stack.md`.
- Development standards codified (2026-07-22): database naming / audit /
  soft-delete standards, UI token & component standards, tech-stack register,
  session workflow with next-session prompts, per-module documentation set,
  `CLAUDE.md` session contract.
- Phase 0 Increment 1 (2026-07-22): core schema spine (`core_tenant_configs`,
  `core_feature_flags`, `core_audit_logs`, `core_query_logs`,
  `core_activities`) via a single Alembic chain; automatic hash-chained audit
  trail on every data change; soft deletes with a global filter; least-
  privilege runtime DB role (`oc_app`, no DELETE anywhere);
  `GET /api/v1/config` (tenant + branding + feature flags, Redis-cached,
  fail-safe OFF, never 500); 31 QA-gate tests + import-linter contracts.
  Hardened by a 34-agent adversarial review (23 confirmed findings fixed).
- Feature-flag rollout note: flags default **OFF**; cohort widenings will be
  recorded here per release.
