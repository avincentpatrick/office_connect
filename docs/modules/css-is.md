# Module: CSS-IS (Client Satisfaction Survey Information System)

## 1. Status

**NOT STARTED — migration planning session pending. Phase slots: 1 (data/auth
promotion) and 8 (full migration).** The live v2.24 build stays on Hugging
Face until migrated in.

**⚠ This module now owns TWO increments that used to belong to Stage D**
(moved 2026-08-09; [`master-plan.md`](../master-plan.md) §4 register row 12):

| Was | Now | Why |
|---|---|---|
| Stage D-3 — CSS-IS reverse-proxied into the shell ("session carries") | **Stage G**, after the Phase 1/2 identity unification | Every shape of it needs an artifact this workspace does not have. §5a. |
| Stage D-4 — `ai_core` promoted to the shared AI service | **Stage G**, with the code it is promoted *from* | You cannot promote code you do not have; and it would ship with no consumer. §5b. |

**Stage G also moved behind Stage H** in the build order for the same reason —
see the master plan's §4 row for the cost that carries.

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
  (author decision recorded in the reconciliation doc §5: promote). **Sequencing
  resolved — §5b.**

### 5a. "Reverse-proxied into the shell (session carries)" — the D-3 kickoff findings (2026-08-09)

Stage D-3 was opened, researched to a decision point, and **moved to Stage G
without code**. What follows is the whole finding, recorded so the next kickoff
starts here instead of re-deriving it. Nothing below is a preference; each item
is a missing artifact or a broken precondition.

**(1) Nothing about CSS-IS is reachable from this workspace.**
`module.css_is` exists only as a seeded, fail-safe-OFF feature flag
(`alembic/versions/0001_core_spine.py`, mirrored in `ops/bootstrap.py`
`DEFAULT_FLAGS`). There is **no `css_*` table, no route, no model, no nav row,
no permission** — every mention of CSS-IS in `office_connect/` is a comment
describing *a separate system that feeds data in* (`core/directory/ingest.py`:
*"decoupled by decision … no code dependency, no live link"*). §3 above already
said the repo is not in this workspace; the search confirms it, and adds that
**no deployment locator exists anywhere in the repo either** — no Space URL, no
host, no env var, no credential. The only path recorded in any source is a dead
local one in the execution plan (`C:\Users\USER\Downloads\css\`). *A proxy route
has nothing to point at.*

**(2) "Session carries" is a property of identity unification, not of plumbing.**
The execution plan makes it conditional, twice: Phase 2 QA is *"one user record
per person platform-wide; logging into the shell and entering CSS-IS requires no
second login"*, and Finding C-3's resolution is *"migrate CSS-IS to PostgreSQL
first (Phase 1), then promote its auth/directory to shared core and repoint
CSS-IS to it (Phase 2), so there is one user store"*. **Those are Phase 1 and 2 —
this module, i.e. Stage G.** Stage D-3 as written asked the session to carry
*before* the unified user store that makes it carry. The dependency was inverted
in the lettering, not in the design.

**(3) All three SSO shapes need an artifact we do not have.** CSS-IS auth is a
stateless HMAC-signed cookie with no server-side store, secret in a local
`.session_secret` file, resolving its identity claim against **CSS-IS's own local
user table** (reconciliation §2.3). Therefore:

| Shape | What it needs | Verdict |
|---|---|---|
| Office-Connect **mints** a CSS-IS cookie | their `.session_secret` | ⚠ **Never pick this as "the easy one."** A shared signing secret makes Office-Connect able to impersonate **any** CSS-IS user *inside CSS-IS's own tamper-evident hash chain* (`rechain_audit.py`) — the one record whose value is that it cannot be forged. Attribution in both systems would become unfalsifiable. |
| Short-lived **signed handoff token** consumed by a new CSS-IS endpoint | a code change in the css-is repo | The correct long-term shape. Buildable only when the repo is in hand — i.e. at Stage G, by which point (2) has already removed the need. |
| **OIDC / OAuth** with Office-Connect as IdP | a whole IdP + CSS-IS changes | Out of scope. The plan's own words: *"Platform-managed accounts now; Google/DOH sign-in is an optional later upgrade."* |

**(4) The embed shape, analysed once.** Recorded because the question is real and
the analysis does not change when the repo arrives:

- **Cross-origin `<iframe>` of the Space — does not work for a session.** CSS-IS's
  cookie becomes a *third-party* cookie and is blocked or partitioned by default
  in Chrome, Safari and Firefox, so the user often cannot log in inside the frame
  at all. Our own `oc_session` is `SameSite=Lax` with `Path=/api` and a host-only
  domain (`core/config.py`), so it never rides a cross-site request either.
  Secondary costs: two sets of nav chrome, and CSS-IS's Ctrl-K palette competing
  with the shell's keyboard.
- **Same-origin path proxy at `/css-is/*` — solves cookies, buys a rewriter.**
  First-party again, but CSS-IS is server-rendered Jinja2 across **~171 routes**
  with root-relative URLs (`/static/js/search.js`, `/admin/ai`, `/activity*`), so
  a path prefix needs an HTML/CSS/JS URL-rewriting layer. It also puts our ASGI
  app in the data path for uploads and `realtime.py` websockets, and opens an
  SSRF / open-proxy surface. Note the platform makes **no outbound HTTP calls at
  all today** — this would be the first, in the request path, against the house
  rule that slow work belongs in the worker.
- **Host-based proxy at the deployment tier — where routing already lives.**
  `Hosting_Target_Clarification.md` §2 already assigns TLS, routing and
  compression to IIS / nginx / Caddy in front of Uvicorn. A same-site host
  (`css.<host>`) makes cookies first-party with **zero** rewriting and zero
  application code. **This is the recommended shape** whenever the question is
  reopened.

**(5) A live link is a NEW data flow the Stage-B PIA does not cover.**
`docs/compliance/pia-stage-b-identity.md` records CSS-IS as *"inbound feed
(feed-only; no code dependency, no live link)"*. An embed, a proxy or a shared
session changes that description. **A PIA amendment is a precondition of shipping
any of them**, not a follow-up (master plan §3.1: the PIA-per-module gate applies
before real data in *any* environment).

### 5b. `ai_core` promotion — sequencing resolved (2026-08-09)

The *decision* stands unchanged (reconciliation §5 #2: **promote**). Only its
slot moved, for two independent reasons:

1. **You cannot promote code you do not have.** master-plan §1.1 #16 says
   *"CSS-IS `ai_core` **promoted**"* — the verb requires the repo. Writing a
   greenfield AI service instead would mean a second implementation to reconcile
   against the real one at Stage G, which is precisely the duplication rule 10
   exists to stop.
2. **It would ship with no consumer.** §1.1 #16's consumer list reads *"query bar
   (only if NL intent ships)"*, and Stage D-1 deliberately shipped a
   **deterministic** matcher with no `ai_core` dependency ([`landing.md`](landing.md)
   §6b). The repo's own standard for this is written down twice — *"one consumer
   is not a pattern"* (ui-standards §3/§4 notes). Zero is fewer.

## 6. Plan

*(The full migration plan is filled at the module's requirements/migration
session. What follows is only the order in which the blockers clear — recorded at
the D-3 kickoff so the session does not re-open the questions in §5a.)*

**The unblock checklist, in order. Each step is a precondition of the next.**

1. **Locate the css-is repo** and record where it lives. §3 has asked for this
   since the module doc was written; §5a is what it costs to keep deferring it.
2. **Record the live deployment locator as configuration** — the Space URL as a
   settings field, fail-safe absent (a missing value must mean *"no CSS-IS"*, the
   same posture `feature_enabled` takes). Today the value exists nowhere in the
   repo.
3. **Phase 1 — SQLite → PostgreSQL** with the per-table-class naive-Manila → UTC
   conversion and the audit re-chain (§4, reconciliation §2.1). The highest-risk
   step in the whole module.
4. **Phase 2 — unify identity**: promote `auth.py`, repoint CSS-IS at the shared
   `core_users` store, move `.session_secret` off the filesystem. **This is the
   step that makes "session carries" true.** After it, §5a's SSO table is moot —
   there is one session because there is one user store, which is what the
   execution plan intended all along.
5. **Only then choose the embed shape** — and per §5a(4) the answer is expected to
   be the deployment-tier host proxy, with a PIA amendment (§5a(5)) landing before
   it does.
6. **Promote `ai_core`** (§5b), by which point the query bar's NL-intent question
   has either shipped a consumer or has not.
