# Module: Foundation (Phases 0–2)

The shared floor everything else — reimbursement included — sits on.
Nothing user-facing precedes it (`references/Phased_Rollout_Assessment.md` §3).

## 1. Scope & status

| Piece | Phase | Status |
|---|---|---|
| Dev environment (Docker, ports, health) | 0 (pre-work) | ✅ done (session 1) |
| Increment 1 — schema spine + conventions + tests | 0 | ✅ done (session 2) — 31 QA-gate tests green, adversarially reviewed |
| Increment 2 — ops: deploy, backup/restore, Celery, explicit-step migrations, git remote | 0 / Stage A | ✅ done (session 4) — proven-restore drill green, worker/beat up, pytest 31/31 |
| Increment 3 — integrations: storage/email drivers, bootstrap CLI, token contract | 0 / Stage A | ✅ done (session 5) — pytest 68/68; local storage round-trip, email drivers + outbox stub, bootstrap CLI (prod-refusing), `/api/v1/config` tokens |
| Increment 4 — spine amendments (master plan §2 Stage A) | 0 / Stage A | ✅ done (session 6) — pytest 132; taxonomy/UACS/holiday+WD engine/compliance calendar/attachments (ClamAV-opt-in)/notification outbox/report lineage/seed framework/observability; **Phase 0 QA gate → tag `phase-0-complete`, first push** |
| Auth / RBAC / staff directory ("one login") | 2 / Stage B | not started |

> **2026-07-23:** sequencing and scope now governed by [`docs/master-plan.md`](../master-plan.md)
> (Stage A = Phase 0 increments 2–4; Stage B = Phase 2). This doc keeps the
> increment detail.

## 2. Source references

- `references/OfficeConnect_Build_Execution_Plan_v1_0.docx` §7 / §12 / §25 (Day-1 items, layout, QA gates)
- `references/Digital_Transformation_Integration_Blueprint.md` §2 (spine: `core_activity` join key, soft references)
- `references/Phased_Rollout_Assessment.md` §3 (foundation floor definition)
- `references/Hosting_Target_Clarification.md` (Windows Server prod substrate)
- Standards: [`database-standards.md`](../standards/database-standards.md) · [`development-workflow.md`](../standards/development-workflow.md)

## 3. Phase 0 build plan

*(Absorbed from the session-2 plan so the repo is self-contained; the old
out-of-repo plan file is superseded by this section.)*

### Increment 1 — schema spine + conventions + tests *(current)*

- **Package restructure** `app/` → `office_connect/` (`core/` + `modules/`
  skeleton); `APP_VERSION` in `office_connect/__init__.py`; import-linter
  contracts in `pyproject.toml` ("core never imports modules; modules never
  import each other").
- **Conventions layer** — `core/base.py`: shared `Base` with the DB standards
  §4 naming convention, `PKMixin` (BIGINT identity), `AuditColsMixin`,
  `SoftDeleteMixin`, `LookupMixin`; `core/time.py` (UTC store / Manila
  display, naive rejected).
- **Alembic** — async `env.py` (NullPool + `run_sync`), single chain,
  migration `0001_core_spine` (tables in §4 below + roles/grants + seeds).
- **Audit chain** — `core/audit.py`: session listeners write hash-chained rows
  to `core_audit_logs` atomically with each flush; `verify_chain()`;
  reconcile with CSS-IS `rechain_audit.py` at Phase 1 (repo not in workspace —
  locate before Phase 1/2).
- **Soft deletes** — `core/soft_delete.py`: global `deleted_at IS NULL`
  filter + `include_deleted` escape hatch + `soft_delete()` helper.
- **Two DB roles** — `oc_dev` (owner/migrations) and `oc_app` (runtime:
  no DELETE anywhere, no UPDATE on append-only tables).
- **`GET /api/v1/config`** — tenant identity + branding + feature flags;
  Redis-cached (30 s); **fail-safe OFF**, never 500.
- **pytest QA gates** — see §6.

### Increment 2 — ops *(revised 2026-07-23 per research — master plan §5)*

Deploy script with live-DB + version-bump + CHANGELOG guards; scheduled
`pg_dump -Fc` backup with **3-2-1 placement** (off-VM copy + periodic offline
copy) **plus one proven restore before real data exists** — the restore drill
also runs `verify_chain()` over the restored audit log (free integrity check);
wire the Celery worker service + first beat task; **migrations as an explicit
deploy step** (`alembic upgrade head` run before app start; the previously
planned migration-on-boot is demoted to a dev-only, env-gated convenience —
multi-worker boot races and crash-loop DDL are a known production failure
mode). **Also: provision the private git remote OFF the future production
hardware** (the repo + Alembic history is a disaster-recovery artifact;
required before the Phase 0 push).

### Increment 3 — integrations + bootstrap

Storage driver abstraction (S-5): Google Drive driver + Shared-Drive
verification, with local-volume driver as the likely production choice
(master plan §4 #3 — deployment-time decision); SMTP + Gmail API two-driver
email abstraction + test-email path, wired behind the notification outbox;
bootstrap CLI (first System Admin; refuses fixtures in prod) + synthetic
fixtures; design-token contract served via `/api/v1/config` (UI standards §2).

### Increment 4 — spine amendments *(new 2026-07-23 — master plan §2 Stage A)*

- `core_activities` hardening + `core_activity_tags` (GAD/CCET/DRR/UHC
  taxonomies, never boolean columns).
- `core_pap_codes` + `core_object_codes` skeletons (per-FY PREXC tree,
  effective-dated, UACS never-reuse semantics; travel = 5-02-01-010-00).
- Holiday & work-suspension calendar (`core_holidays`) — the single
  working-day engine for every deadline.
- `core_compliance_deadlines` — the statutory calendar as data (master plan
  §3.4 seed).
- Core attachments service (upload pipeline, content-addressed store,
  fail-closed downloads; ClamAV joins the compose stack).
- Notification outbox tables + in-app notification center schema.
- Report-lineage table (Blueprint Day-1 #17).
- Seed framework: idempotent, environment-aware; named owner + cadence for
  external datasets (PSGC quarterly, holiday proclamations annually,
  GRDS/threshold revisions).
- `docs/compliance/` (PIA template, processing register, breach runbook,
  retention schedule) + `docs/operations/` (runbooks) scaffolds.
- API-versioning + observability standards (structured JSON logs w/ request
  IDs; self-hosted error tracker in compose).

## 4. Spine tables (pluralized per DB standards §2)

| Table | Class | Notes |
|---|---|---|
| `core_tenant_configs` | business | name, short_name, display timezone, `branding` JSONB |
| `core_feature_flags` | lookup | `key` unique (partial, live rows), `enabled` default **false**; `is_active` retires a row, `enabled` is the flag state — a feature is ON only if both |
| `core_audit_logs` | append-only | hash chain (`prev_hash`/`row_hash`), actor, request, old/new JSONB; PK `GENERATED ALWAYS` |
| `core_query_logs` | append-only | privacy-preserving (ids/params only); populated from Phase 2 middleware |
| `core_activities` | business | join-key registry (Blueprint §2.2): title, ppa_code, division/section (BIGINT, FKs in Phase 2), dates, venue, status enum, `custom` JSONB |
| `core_activity_tags` | lookup | configurable GAD/CCET/DRR/UHC taxonomy vocabulary (never boolean cols) — Inc 4 |
| `core_activity_tag_assignments` | business | activity ↔ tag link (multi-tag), FK to activities+tags — Inc 4 |
| `core_pap_codes` | lookup | per-FY PREXC tree (self-ref parent), effective-dated, UACS never-reuse — Inc 4 |
| `core_object_codes` | lookup | 10-digit UACS object codes (travel = 5-02-01-010-00), effective-dated — Inc 4 |
| `core_holidays` | lookup | PH holidays + work suspensions; feeds the working-day engine (`core/workdays.py`) — Inc 4 |
| `core_compliance_deadlines` | lookup | statutory calendar (master-plan §3.4) as effective-dated, tenant-overridable data — Inc 4 |
| `core_attachments` | business | content-addressed files: polymorphic holder, dual SHA (original+sanitized), scan status, retention — Inc 4 |
| `core_notifications` | business | notification outbox + in-app center (channel discriminator); status queued→sent/dead — Inc 4 |
| `core_notification_deliveries` | append-only | per-attempt delivery log (dead-letter substrate); REVOKE UPDATE — Inc 4 |
| `core_report_lineages` | append-only | provenance of every generated output (Blueprint #17); REVOKE UPDATE — Inc 4 |

*Increment-4 core services (built on the tables above):* the working-day engine
(`core/workdays.py`), the attachments service (`core/attachments/` — pipeline +
injectable ClamAV scanner + retention), the notification outbox/dispatch
(`core/notifications/` — replaces the Inc-3 stub, signature-stable), the report-
lineage helper (`core/report_lineage.py`), the seed framework (`core/seeds/`),
and observability (`core/logging.py` JSON logs + request IDs, `core/observability.py`
fail-safe error tracker). `core_attachments.(holder_kind, holder_id)` is a
**sanctioned polymorphic reference** (no FK — database-standards §3); modules
resolve authorization through the entity named by `holder_kind`.

## 5. Phase 2 plan (outline — detailed at its build sessions)

Shared auth patterned on CSS-IS `auth.py`/`ratelimit.py` semantics but built
per `docs/research/round1/auth-rbac-onprem.md`: Redis server-side sessions,
Argon2id, NIST 800-63B-4 password policy (length 12+ + blocklist; **no
composition rules / no forced rotation** — the reference's "letter+number"
recorded as a deviation), throttle-not-lockout, custom-header CSRF,
break-glass local admin, TOTP MFA for approver/admin roles (NPC Circular
2023-06). RBAC: permission strings + role→permission tables +
**org-unit-scoped grants**; delegation/OIC table (on-behalf-of); maker-checker
DB checks (DV Boxes A/B/C pairwise distinct); read-only **auditor role** (COA
Res. 2020-034) + printable chain-verification report. Staff directory:
**greenfield core tables seeded via CSV import from a CSS-IS export** (no code
dependency; recommended default — confirm at Stage B kickoff). Deferred FKs
(`*_by`, `division_id`, `section_id`) in one migration; query-log middleware;
audit-payload SPI policy decision executes here (master plan §4 #4).

**Open decisions (resolve before Stage B starts):**
- **`core_users` vs `core_staff`** — one identity table or auth-users vs
  staff-directory split; also settles the irregular plural ("staff").
- **Directory seed detail** — greenfield + CSV import is the recommended
  default (`references/Reimbursement_First_Dependency_Analysis.md` §7;
  master plan §4 #1).

## 6. QA gates (Phase 0)

- `alembic upgrade head` idempotent (×2)
- Every table carries its mandatory column set; append-only tables carry none
  of `updated_*`/`deleted_*`
- Audit tamper attempt detected by `verify_chain`
- `oc_app` denied UPDATE/DELETE on logs and DELETE everywhere
- Soft-delete filter + escape hatch work; soft delete produces an audit row
- UTC↔Manila round-trip; naive datetimes rejected
- `/api/v1/config` fail-safe OFF, never 500
- `lint-imports` green
- *(Increment 2 adds — all verified session 4:* one proven backup restore incl.
  `verify_chain()` on the restored DB *(the drill seeds a real ≥3-link chain
  first, so the check is never vacuously green)*; explicit-step migration proven
  from a wiped volume; dev-convenience advisory-locked boot migration; Celery
  worker/beat up with the nightly-backup task firing end-to-end; deploy guard
  passes `--mode dev` and blocks `--mode release` on the `.devN` version.)*
- *(Increment 3 adds — all verified session 5:* local-volume storage
  round-trips a file (content-addressed, atomic write, dedup) + factory driver
  selection; email drivers (SMTP/Gmail/log) send/build correctly + auto-select;
  notification outbox stub routes through the selected driver; `send-test-email`
  path works (logs in dev); bootstrap CLI `init`/`create-admin`/`load-fixtures`/
  `send-test-email` — idempotent, `load-fixtures` **refused in production**;
  `create-admin` record lands in the non-public tenant `settings` bag and is
  **never** served by `/api/v1/config`; `/api/v1/config` serves the `tokens`
  contract (neutral defaults + branding merge, present even under the DB
  fail-safe); WCAG-AA contrast on the default palette; migration 0002 idempotent
  + reversible.)*
- *(Increment 4 adds — all verified session 6, **pytest 132/132, lint-imports
  3/3**:* full chain `0001→0008` idempotent (×2) + clean downgrade-to-base →
  re-upgrade; every new table carries its mandatory column set; the two new
  append-only tables (`core_notification_deliveries`, `core_report_lineages`)
  carry no `updated_*`/`deleted_*` and `oc_app` is denied UPDATE/DELETE on them;
  holiday-calendar working-day math correct across weekend/holiday/suspension/
  special-working; compliance-deadline seed (22 rows) + all reference datasets
  load idempotently (re-run = 0 changes) and load under `APP_ENV=production`;
  attachment pipeline round-trip incl. **EXIF strip + HEIC→JPEG** and fail-closed
  download (infected/oversized/bad-type/SVG rejected; pending denies); ClamAV is
  opt-in via a compose profile, the gate proven with an injected scanner;
  notification outbox persists + dispatches with retry + dead-letter (inline
  **and** celery→worker verified end-to-end); report lineage is unaudited +
  immutable; JSON logs carry the request id.)*

## 7. Decisions log

- **2026-07-23 (Increment 4 spine amendments — session 6)** — the last Phase-0
  increment; closed at the Phase 0 QA gate (tag `phase-0-complete`, first push).
  Built in independently-committable groups; pytest 132/132, lint 3/3. Key
  decisions (user-confirmed at session start):
  - **Attachments = full pipeline now, ClamAV opt-in.** The whole pipeline
    (magic-byte allowlist JPEG/PNG/WebP/PDF, size cap, SHA-256 content-address,
    Pillow re-encode + EXIF/XMP strip, HEIC→JPEG, decompression-bomb guard) +
    `core_attachments` land now on the Inc-3 `StorageDriver`. Scanning is an
    **injectable `Scanner`** with a fail-closed `NullScanner` (deny-in-prod,
    clean-in-dev) + a real `ClamAVScanner`; ClamAV joins compose behind a
    `profiles: [clamav]` profile, so default `up`/CI skip its ~1 GB DB and the
    gate proves "infected rejected" via an injected scanner. **Dual SHA**:
    `sha256` = the original received bytes (audited evidence, dedup key, scanned);
    `sanitized_sha256` = the re-encoded derivative served for images (EXIF never
    leaves via the app). The **authenticated HTTP download router defers to
    Stage B** (no auth yet) — the download is a service method taking an
    `authorize` hook; scan+re-encode run deferred in a Celery task (`ops/`), core
    stays pure.
  - **Retention ≠ soft delete; no auto-purge ever.** `retention_class` /
    `retention_starts_at` / `legal_hold`; `retain_until` is derived; a
    disposal-eligibility **report** (never a purge) lists eligible records for a
    human NAP process (database-standards §8; `docs/compliance/retention-schedule.md`).
  - **Notifications = durable outbox, signature-stable.** `send_notification` /
    `send_test_email` keep their Inc-3 signatures but now **persist a
    `core_notifications` row and dispatch** (inline by default; the running app
    enqueues to the worker in `celery` mode after commit, via an injected
    enqueuer — `ops`→`core`, keeping `core` free of Celery). One table serves the
    outbox **and** the in-app center via a `channel` discriminator; the
    append-only `core_notification_deliveries` is the dead-letter/failed-jobs
    substrate; dedup via `meta['dedup_key']` (app check + partial-unique backstop).
    `send_test_email` forces inline (a diagnostic must send now, not "queued").
    Per-user prefs + the WebSocket bell defer to Stage B/D (schema already carries
    `recipient_user_id`/`read_at`).
  - **UACS/PREXC + taxonomies as data, effective-dated, never boolean.** Tags
    (GAD/CCET/DRR/UHC), PAP codes (per-FY tree), and object codes are configurable
    rows; codes are deactivated, never reused; deadlines carry two partial-unique
    indexes (one platform default per `(code, effective_from)` where `tenant_id
    IS NULL`, one override per tenant).
  - **Working-day engine is pure + DB-backed.** `core/workdays.py` math takes a
    non-working `set[date]` (unit-testable, no DB); `load_nonworking_dates` reads
    `core_holidays`. Weekends always non-working; `special_working` days are not
    (documented Phase-0 simplification: a special-working day on a weekend is not
    promoted).
  - **Report lineage folded into core, append-only + unaudited** (master-plan §4
    #7 — no `rpt_` tables). It is itself an immutable log (REVOKE UPDATE), so it
    is in `_UNAUDITED` like the query log.
  - **Seed framework = idempotent + environment-aware + named owner/cadence.**
    `core/seeds/` datasets (pure) + an `ops` runner (`load-reference`) upsert by
    natural key (insert/update-changed/skip-unchanged). Reference data (public
    law/config) loads in every env; synthetic fixtures stay non-prod
    (`load-fixtures`). Named cadences: PSGC quarterly, holiday proclamations
    annually, GRDS/threshold revisions on-revision.
  - **Observability = JSON logs now, tracker as a profile.** Stdlib JSON logging
    + request-id contextvar (no new dep); uvicorn loggers routed through it so
    every line is JSON. Error tracking (`sentry-sdk`, GlitchTip-compatible) is
    **fail-safe optional** (active only with `SENTRY_DSN`); GlitchTip runs behind
    a compose `observability` profile, full wiring deferred to Stage C. New
    `docs/standards/api-standards.md` documents the `/api/v1/` versioning +
    error-envelope + observability contract.
  - **Compose services added behind profiles** (never in default `up`/CI):
    `clamav` (attachments scan), `glitchtip`/`glitchtip-db`/`glitchtip-worker`
    (error tracker) — internal-network posture, matching production.
- **2026-07-23 (Increment 3 integrations + bootstrap — session 5)** — storage/
  email drivers, notification outbox stub, bootstrap CLI, and the design-token
  contract built and verified (pytest 68/68, lint-imports 3/3). Key decisions
  (user-confirmed at session start):
  - **Storage default = local content-addressed volume** (on-prem posture,
    master plan §4 #3 resolved). One `StorageDriver` interface
    (`core/storage/`); the **Google Drive** driver is fully implemented and kept
    for tenants that want it, with **Shared-Drive verification** (refuses a My
    Drive folder — service-account uploads there are unrecoverable). `key` = the
    content SHA-256; blob `delete` is physical and reserved for the Increment-4
    attachments/retention layer, never a business row.
  - **Email = two real drivers + a dev fail-safe.** SMTP (stdlib `smtplib`, the
    default transport) and Gmail API (domain-wide delegation) behind an
    `EmailDriver` interface; a **`log`** driver records instead of sending and is
    **auto-selected when no SMTP is configured**, so a fresh dev stack exercises
    the path without a mail server. Drivers sit behind a **notification outbox
    stub** (`core/notifications/`) — the durable `core_notifications` table +
    Celery retry + notification center are **Increment 4**; the caller-facing
    seam signature won't change (Rule 10 — one notifications service, no
    duplication).
  - **Google libraries added now** (`google-api-python-client`, `google-auth`,
    `google-auth-httplib2`) — pure-Python, imported **lazily** inside the drivers
    so importing the modules needs neither the packages nor credentials; the
    local + SMTP defaults never pay for Google. Google drivers are unit-tested
    with the client mocked (no real creds in dev).
  - **Bootstrap "System Admin" deferred to Stage B.** No `core_users` table
    exists yet (the `core_users`-vs-`core_staff` identity split is a Stage B
    decision, §5), so `create-admin` **records the designated admin's email/name**
    into a new **non-public** `core_tenant_configs.settings` JSONB (migration
    0002) for Stage B to promote — it does not create a login. `settings` is
    **never** served by `/api/v1/config` (branding stays the only public bag), so
    the admin email cannot leak to the unauthenticated endpoint. Bootstrap DB
    writes go through the least-privilege `oc_app` role via `OCSession`, so
    they're audited like ordinary app writes; `load-fixtures` hard-refuses
    `APP_ENV=production`.
  - **Design tokens = concrete WCAG-AA neutral defaults + branding merge.**
    `NEUTRAL_TOKENS` (`core/ui/tokens.py`) is the single source of truth, served
    under `tokens` in `/api/v1/config` and always present (even the DB fail-safe
    returns the full neutral set). Tenant `branding.tokens` overrides are
    deep-merged; unknown keys ignored. This fills the *values* half of
    ui-standards §9 early; the Tailwind/component mapping (§7) stays deferred to
    the first React surface.
- **2026-07-23 (Increment 2 ops — session 4)** — backup/restore + Celery +
  explicit-step migrations built and verified. Key decisions:
  - **pg client pinned to major 16** (PGDG apt, base-codename-derived) to MATCH
    the PG16 server — a *newer* pg_dump (17) emits `SET transaction_timeout`
    which a PG16 server rejects on restore, so "client newer than server" is
    NOT safe for the dump→restore round-trip. Bump the `db` image tag and the
    client together.
  - **Backups + scratch-DB create/drop run as `oc_dev`** (owner/superuser via
    `MIGRATION_DATABASE_URL`); `oc_app` is SELECT-only with no `CREATEDB`.
  - **The restore drill seeds a real audited chain first** (insert+update+
    soft_delete via `OCSession`) so `verify_chain()` walks ≥3 real links — a
    freshly-migrated DB's chain is empty and would pass vacuously. Never seeds
    when the chain is non-empty or `APP_ENV=production`.
  - **`swap_database` must render with `hide_password=False`** — SQLAlchemy's
    `str(URL)` masks the password as `***`, which broke asyncpg auth on the
    scratch-DB URL (the CLI tools were unaffected as `libpq_env` reads the raw
    `url.password`).
  - **New `office_connect/ops/` package** (backup, restore drill, deploy guard,
    dsn); a new import-linter contract keeps `core` from importing `ops`/
    `worker` (lint-imports now **3/3**).
  - **Celery broker/results on Redis db 1/2** (app config cache stays on db 0);
    the backup task is pure-subprocess (no async loop in the worker). **Beat is
    a dedicated single-replica service** — never `--scale beat`.
  - **Boot migration demoted to a dev-only, env-gated convenience**
    (`OC_MIGRATE_ON_BOOT`, default OFF) in a container **entrypoint** (once per
    container, not per uvicorn worker), advisory-locked; hard-refused when
    `APP_ENV=production`. Prod runs the explicit `alembic upgrade head` step.
  - **Deploy guard** = cross-platform Python in-container (`--mode dev|release`);
    git-tag check stays host-side; runbooks in `docs/operations/` are POSIX-sh
    authoritative (prod = Ubuntu VM), `scripts/deploy.ps1` is the dev wrapper.
  - **Private git remote = GitHub private**; off-box backup target = second/
    external disk (host-side copy step, documented). Remote is *provisioned*
    now; first push fires at the Phase 0 gate (push-per-phase).
- **2026-07-22** — 9 standing dev rules issued; naming = prefixed **plural**;
  soft deletes on all business tables (append-only exception); commit per
  session / push per phase; PK = BIGINT identity (no UUIDs); `*_by` columns
  plain BIGINT until Phase 2 FKs; audit = app-level session listeners
  (not triggers), hash payload includes app-set `created_at`.
- **2026-07-23** — Master plan v1 adopted (`docs/master-plan.md`): Increment 2
  revised (explicit-step migrations; 3-2-1 backups; off-box git remote),
  Increment 4 added (spine amendments); production substrate corrected to
  **Hyper-V Ubuntu VM + Docker Engine** (not Docker Desktop / WSL2 / native
  Windows services — see master plan §3.2 and tech-stack.md); Rule 10
  ("shared service first") adopted; core workflow engine will be built once at
  reimbursement R-4 and shared platform-wide.
- **2026-07-22 (post-review)** — floats stringified in audit payloads (jsonb
  numeric normalization would break the chain); relationships never use
  `delete-orphan`; ORM bulk UPDATE/DELETE blocked (`allow_unaudited` escape
  hatch for maintenance); degraded config payloads never cached;
  `APP_VERSION` carries a `.devN` suffix until the phase gate promotes it;
  known accepted limits: advisory lock held first-flush→commit (keep audited
  transactions short), `session.get()` identity-map hits can return
  soft-deleted objects, changing `OC_APP_PASSWORD` post-migration needs a
  manual `ALTER ROLE`.

## 8. Manual test guide (Phase 0)

Plain-language walkthrough proving the foundation floor end-to-end. Run from the
repo root with the stack up (`docker compose up -d`; ports 8001/5432/6380).

1. **Stack is healthy.** Open <http://localhost:8001/health> → `{"status":
   "healthy", ...}`. Open <http://localhost:8001/api/v1/config> → all module
   flags `false` (fail-safe OFF); no `bootstrap_admin`/admin email present.
2. **Migrations are clean.** `docker compose exec app alembic upgrade head`
   twice → the second run does nothing (idempotent). Head is `0008`.
3. **Automated gates.** `docker compose exec app pytest -q` → all green;
   `docker compose exec app lint-imports` → 3 contracts kept.
4. **Seed the reference data.** `docker compose exec app python -m
   office_connect.ops.bootstrap load-reference` → activity taxonomies, object
   codes, PAP skeleton, PH 2026 holidays, and the 22 statutory deadlines load.
   Re-run → every dataset shows `+0 ~0` (idempotent).
5. **Working-day math.** (Covered by `tests/test_calendar_workdays.py`.) A
   deadline landing on a weekend rolls to Monday; crossing a regular holiday adds
   a day; a work-suspension mid-window is skipped; a special-working day counts.
6. **Attachment round-trip.** Upload a JPEG-with-EXIF through the service, scan
   it (dev NullScanner → clean), download it → the served bytes have **no EXIF**
   (verified end-to-end; see `tests/test_attachments_service.py`). An infected/
   oversized/SVG/unknown file is rejected; a `pending` file cannot be downloaded.
   To scan with real ClamAV: `CLAMAV_HOST=clamav docker compose --profile clamav
   up -d` then `docker compose exec worker python -m office_connect.ops
   scan-pending`.
7. **Notifications.** `docker compose exec app python -m
   office_connect.ops.bootstrap send-test-email --to you@example.com` → prints
   `"driver": "log"` (dev) and persists a `core_notifications` row that dispatches
   to `sent` with a `core_notification_deliveries` row. In the running app
   (celery mode) the worker processes the dispatch task.
8. **Audit integrity.** The restore drill re-runs `verify_chain()` over a
   restored dump: `docker compose exec worker python -m office_connect.ops
   backup-and-drill` → `verify: ok`.
9. **Structured logs.** `docker compose logs --tail=20 app` → JSON lines; a
   request made with `-H "X-Request-ID: probe"` shows `"request_id": "probe"` on
   its access-log line.
10. **Coexistence.** Laragon `dev_pims` (80/3306/8000) is untouched.
