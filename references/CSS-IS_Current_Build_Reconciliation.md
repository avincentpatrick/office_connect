# CSS-IS (Module 1) — Current-Build Reconciliation

**Companion to:** `OfficeConnect_Build_Execution_Plan_v1_0.docx` (v1.0, June 2026 — the single source of truth) and `Source_Grounding_and_Understanding.md`
**Purpose:** Re-baseline the plan's snapshot of CSS-IS (§2.3, §18) against the **actual current build** so the Module 1 migration (Phases 1, 2, 8) is planned against reality, not against a four-week-old snapshot.
**Method:** Direct read of the `css-is` repository at `APP_VERSION = 2.24` (CHANGELOG top entry `2026-07-20`). Every claim below cites `file:line`.

This document does **not** change any locked decision in the execution plan. Where the code and the plan diverge, it flags the divergence and states the integration consequence; where a genuine choice is now required, it is listed in §5 for the author. **The execution plan governs.**

---

## 0. Headline

The plan's Module-1 description is **still directionally correct** — same framework, same locked scoring engine, same NAV_GROUPS discipline — but the code has moved on by ~15 releases since the plan was frozen. Three items materially change the Module-1 migration and one contradicts a platform convention:

1. **Timestamps are stored as *naive local Manila* time, not UTC.** This sharpens Finding **C-1** from "avoid a double-shift" into "the migration must perform a real local→UTC conversion, on top of history that was *already* shifted once." This is the highest-risk integration detail.
2. **`storage.py` is raw `sqlite3` with a hard-coded DB path** — there is no env-var driver switch and no SQLAlchemy layer yet. The plan's "rollback = flip the DB env var" (§18.1, Q9) and "SQLAlchemy async pool" (§17.1) describe a target state that must be *built*, not merely *configured*.
3. **An AI layer already ships in production** (`ai_core.py`, Gemini + Groq + HF fallback, `/admin/ai`, `ai_interaction`/`ai_config` tables, a DB-backed daily budget). The plan treats AI as a future layer (§3.1 "Future-proof for AI", §14.7). It is here now and needs a home in the platform.
4. **The public survey form is bilingual (English + Filipino).** This contradicts Minor Finding **M-3** ("Interface language is English across all modules").

---

## 1. Snapshot: Plan Assumption vs. Current Reality

| Attribute | Plan snapshot (§2.3 / §18, June 2026) | Current build (v2.24, July 2026) | Verdict |
|---|---|---|---|
| Framework | FastAPI + Jinja2, server-rendered | FastAPI + Jinja2 (`app.py:52`) | ✅ Unchanged |
| Web server | single-worker uvicorn | uvicorn (`requirements.txt`) | ✅ Unchanged |
| Database | SQLite | SQLite via raw `sqlite3` (`storage.py:26,41`) | ✅ SQLite — see §2.2 for the *how* |
| `app.py` size | ~7,654 lines | **11,546 lines** (`wc -l app.py`) | ⚠️ +51% |
| Route count | 126 routes | **~171 routes** | ⚠️ +36% |
| Scoring engine | `css_is_engine.py`, **locked** | Locked; 3 survey types intact (`css_is_engine.py:16-18`) | ✅ Unchanged |
| Survey types | ARTA Walk-in 1–5; Activity SERVQUAL 1–7; RP SERVQUAL 1–7 | Identical (`css_is_engine.py:16-18,34-38`) | ✅ Unchanged |
| Navigation | NAV_GROUPS → top nav + Ctrl-K palette, role-filtered | NAV_GROUPS present (`app.py`, `ux_handoff.py`); Ctrl-K palette live (`static/js/search.js:280`) | ✅ Unchanged |
| Auth | production-tested `auth.py` | HMAC-signed stateless cookie, no server-side store (`auth.py:6-7,103-107`) | ✅ Present; see §2.3 |
| Audit | `rechain_audit.py`, tamper-evident hash chain | `sha256` prev_hash/row_hash chain (`rechain_audit.py`) | ✅ Present |
| Timezone convention | "already ran a one-time +8h history shift" (C-1) | Stores **naive local (UTC+8)**; `fix_timezone_history.py` already applied (`tzutil.py:7-18`) | ❗ See §2.1 |
| Staff / RP directory | seed for shared Staff Directory | Present (survey/resource-person directory) | ✅ Unchanged |
| AI | future layer | **Already in production** (`ai_core.py`, `/admin/ai`) | ❗ New — §3.1 |
| Language | English-only (M-3) | **English + Filipino** public form (`i18n.py:1,26`) | ❗ Conflicts M-3 — §3.2 |

---

## 2. Integration Hazards (re-baselined from the code)

### 2.1 Timezone — Finding C-1 is real and *sharper* than the plan assumed  *(highest risk)*

The plan (§18.1, Q9, C-1, Phase 1 QA) warns against a **double-shift** when converting local→UTC, on the theory that CSS-IS "already ran a one-time +8h history shift." The code confirms the shift happened **and** clarifies the current convention, which is more consequential than the plan states:

- CSS-IS **does not store UTC.** Every persisted stamp is **naive local Philippine wall-clock (Asia/Manila, UTC+8)** written as an ISO string, deliberately naive so it text-compares against other naive strings already in the DB (`tzutil.py:5-8,28-37`). Offset is env-overridable via `CSS_TZ_OFFSET` (default 8) (`tzutil.py:25`).
- `fix_timezone_history.py` already ran a **one-time forward shift** of the *purely runtime-generated* logs that a UTC host had written 8 h behind — `audit_log.ts`, `feedback_update.ts`, `spot_feedback.*` — and **re-chained `audit_log`** afterward because the hash chain covers `ts` (`fix_timezone_history.py:1-19`).
- **Mixed tables** (`response.submitted_at`, `form_instance/event/*.created_at`, `attendee.consent_at/purged_at`, etc.) hold a **mix** of live HF writes (UTC, 8 h behind) and spreadsheet-imported rows (already local) — shifted only opt-in via `--since` (`fix_timezone_history.py`, "MIXED TABLES" block).

**Consequence for Phase 1.** The plan's target convention is "UTC `timestamptz` stored, Asia/Manila displayed" (§14.5 hardcoded; Phase 0 QA). CSS-IS's current convention is the opposite (naive local stored, local displayed). So the SQLite→Postgres migration is **not** a no-op text copy into `timestamptz`; it must:
  1. Treat existing values as **naive Asia/Manila** and localize→UTC **exactly once** (subtract 8 h) on the way into `timestamptz`.
  2. Account for the fact that `fix_timezone_history.py` **already normalized** the runtime-log tables to local — so those are safe to localize as a block, while the **mixed tables may still contain un-shifted UTC rows** and cannot be blanket-shifted. The Phase-1 boundary spot-check (plan: "rows straddling the date of the +8h shift … none off by 8 or 16 hours") must be run **per table class**, not globally.
  3. Preserve the `audit_log` hash chain: because the chain covers `ts`, any timestamp transform must **re-chain** (the repo already has `rechain_audit.py` for exactly this) and re-verify.

This is the one place where "seamless" depends on getting arithmetic right on data that has already been touched once. Recommend: migrate through a script that classifies each timestamp column as *runtime-log (already local)*, *import-seeded (already local)*, or *mixed (inspect per-row)*, and validate with the plan's parallel read-only diff before cutover.

### 2.2 `storage.py` is thinner than "the abstraction lever" implies

The plan calls `storage.py` "the lever" for the DB swap (§18.1, Q9) and assumes a "config flip of the DB env var" for rollback and a "SQLAlchemy async pool, size 10 / overflow 20" at runtime (§17.1). The code shows:

- Direct `sqlite3` throughout (`storage.py:26`), opened by `connect(db_path="css_is.db")` — the path is a **function default, not an environment variable** (`storage.py:40-41`). There are ~33 SQLite-specific constructs (WAL/`AUTOINCREMENT`/`journal_mode`) in the module.
- No SQLAlchemy and no async pool anywhere in the runtime.

**Consequence.** `storage.py` *is* a genuine single choke-point (good — the migration surface is one module), but the plan's "env-flip rollback" and "async pool" are **build tasks inside Phase 1/2**, not pre-existing capabilities. The Phase-1 audit the plan already mandates ("audit storage.py for SQLite-specific behaviour first") should explicitly add: introduce the `DATABASE_URL`-style env switch, and decide whether Postgres access goes through SQLAlchemy (plan's assumption) or `psycopg` directly (closer to the current raw-cursor style). The rollback story ("flip back to SQLite") only exists once that env switch is built.

### 2.3 Auth is stateless HMAC cookies — promotable, with one caveat

`auth.py` issues a **tamper-proof HMAC-signed session cookie with no server-side session store** (`auth.py:6-7,103-107`), using a local `.session_secret` file. This matches the plan's intent to promote `auth.py` + `ratelimit.py` to core (Q14, §14.1) and is a clean fit. Caveat for Phase 2: the plan requires the secret to live in **HF Space secrets** (§10.1) — the current file-based `.session_secret` must move to the injected secret, and the "one user record per person on the unified Postgres store" precondition (Q14) means the cookie's identity claim must resolve against the shared user table, not CSS-IS's local one.

### 2.4 Scale drift changes the React-migration estimate (Phase 8)

`app.py` grew from ~7,654 to **11,546 lines** and routes from 126 to **~171**. The strangler-fig plan (Q10, Phase 8) sequences by traffic and is unaffected in *approach*, but the **surface to migrate is ~35–50% larger** than the plan sized. Re-scope Phase 8/10 screen inventory against the current route list before committing dates.

---

## 3. New Capabilities Not in the Plan's Snapshot

### 3.1 AI layer — already in production (plan treats AI as future)

`ai_core.py` is a full free-tier AI integration: a single `ask()` entry point that gates on config/mode/feature, **rate-limits, spends a DB-backed daily budget**, calls **Google Gemini** with an optional **Groq fallback** (and HF edge-retry shielding per CHANGELOG v2.18–v2.24), and logs every outcome to an `ai_interaction` table surfaced at **`/admin/ai`**; config lives in `ai_config` (`ai_core.py:1-20,70,84,141,168`). The contract is "try AI → on any `AIError` → deterministic fallback → never a user-facing error."

This overlaps directly with the plan's **§14.7 privacy-preserving query log / future AI training set** and the §15 query-bar vision. Integration questions the plan did not anticipate (it assumed no AI existed yet):
- Where does `ai_config` / the daily budget / `ai_interaction` live in the platform — Module-1-local, or promoted to a shared **AI service** the universal query bar (§15) also calls?
- Does the platform's anonymous query log (§14.7) subsume or sit beside `ai_interaction` (which logs per-call diagnostics, not anonymized queries)?
- The plan's "fail-safe OFF" flag discipline (§14.5) should absorb `ai_core`'s existing mode/feature gates rather than duplicate them.

**Recommendation:** treat the AI layer as a fourth thing CSS-IS brings into the merge (alongside `auth`, `rechain_audit`, the directory) and decide its ownership in Phase 2/3 when the shared query bar is designed — not during the Phase-1 DB migration.

### 3.2 Bilingual public form conflicts with M-3

`i18n.py` provides English↔Filipino for the **public respondent survey form** — `LANGS = ("en", "fil")`, language chosen from a `lang` cookie → `Accept-Language` → English default; SQD items use the official ARTA Harmonized CSM Tagalog wording (`i18n.py:1,12-13,19,26`). The plan's **M-3** states "Interface language is English across all modules." These conflict for the respondent-facing surface (staff-facing UI remains English).

**This is an author decision (see §5).** Note it is *well-grounded*: an ARTA CSM instrument in the Philippines is normally offered in Filipino to respondents, so keeping the bilingual public form is likely correct — but it means M-3 should be scoped to "staff-facing interface English; respondent-facing surveys may be localized," not struck silently.

### 3.3 Activity module + data-quality tooling (partly anticipated)

- **Activity module** — `activity_admin.py`, `activity_messages.py`, with `/activity*` routes (`app.py:70-71,6392+`). This is capability beyond the three survey types the plan enumerated; "full feature parity" (§18) must now include it.
- **Data-quality tooling** — `harmonize.py`, `name_cleanup.py`, `consolidate_titles.py`, `merge_duplicate_attendees.py`, `reference_match.py`, `retention.py`, plus `daily_backup.py`/`pull_backup.py`. These **fulfill Minor Finding M-4** ("data-quality tooling ships *with* backups and revert scripts") — a plan expectation the current build already meets. Good news, not drift; migrate them with their revert paths intact.
- **Other since-snapshot modules:** `ux_handoff.py`, `ui_telemetry.py`, `tours.py`, `realtime.py`, `qa_rules.py`, `csm_report.py`. `realtime.py` is a foothold toward the plan's WebSocket notification engine (§14.8, §17.2) but must be re-checked for the plan's **Redis Pub/Sub multi-worker** requirement (a single-worker SQLite app has not needed it yet).

---

## 4. Updated Module-1 Migration Checklist (deltas to the plan's phases)

Only the **deltas** vs. the plan are listed; everything else in Phases 1/2/8 stands.

**Phase 1 (SQLite → Postgres)**
- [ ] Classify every timestamp column as *runtime-log (already local)* / *import-seeded (already local)* / *mixed (per-row inspect)* before any conversion; localize naive-Manila→UTC **once**; re-chain and re-verify `audit_log` (§2.1).
- [ ] Build the `DATABASE_URL` env switch and rewrite `storage.py` onto a **SQLAlchemy async pool** (§5 decision 3); the "rollback = env flip" story does not exist until this lands (§2.2).
- [ ] Run the plan's boundary spot-check **per table class**, not globally.

**Phase 2 (shared core)**
- [ ] Move `auth.py`'s `.session_secret` to HF Space secrets; resolve cookie identity against the unified Postgres user store (§2.3).
- [ ] Fold `ai_core`'s mode/feature gates into the platform feature-flag table rather than duplicating them (§3.1).

**Phase 3 (landing + query bar)**
- [ ] Promote `ai_core` to a shared AI service behind the query bar (§5 decision 2); reconcile `ai_interaction` diagnostics with the §14.7 anonymized query log (§3.1).

**Phase 8 (React strangler-fig)**
- [ ] Re-inventory screens against the current ~171 routes, not 126 (§2.4).
- [ ] Preserve the bilingual public form and its `lang` toggle (§5 decision 1, §3.2).

---

## 5. Author Decisions — Resolved (2026-07-20)

All three surfaced decisions are now settled by the author. They are recorded here as binding for the phases they affect.

1. **Bilingual survey (M-3) — DECIDED: keep bilingual.** The English+Filipino respondent form carries through migration (ARTA-standard practice, already built). **M-3 is re-scoped:** "staff-facing interface is English; respondent-facing surveys may be localized." Phase 8 must preserve the `lang` toggle and the ARTA Harmonized CSM Tagalog wording when the public form moves to React (`i18n.py`, §3.2).
2. **AI layer ownership — DECIDED: promote to shared.** The existing `ai_core` (Gemini/Groq, budget, `ai_interaction`, `/admin/ai`) is promoted to a shared platform AI service behind the §15 query bar and §14.7 query log; its config/budget/log tables become platform-level. Settled in **Phase 3**, not during the Phase-1 DB migration (§3.1).
3. **Postgres access layer — DECIDED: SQLAlchemy async.** The Phase-1 `storage.py` rewrite adopts a SQLAlchemy async pool (plan §17.1), matching DMWIS's async model, rather than raw `psycopg`. This is a larger rewrite of the current raw-cursor code but keeps one access layer platform-wide (§2.2).

---

## 6. What This Confirms About Module 1

1. **The plan's core Module-1 thesis holds:** same stack, locked scoring engine, one clean DB choke-point, promotable auth/audit/directory. Migration remains tractable and "seamless" is achievable.
2. **The single riskiest detail is timezone**, and it is riskier than the plan's snapshot implies — the store is naive-local, history was already shifted once, and the tables are not uniform. Get §2.1 right and Phase 1 is de-risked.
3. **The build has grown two things the plan did not budget for** — a live AI layer and a bilingual respondent surface — both of which need a decision *before* the phases that touch them, not during.

---

*Prepared as a current-build reconciliation companion to the Build Execution Plan. Evidence is cited to `css-is` at `APP_VERSION = 2.24`. If any statement here conflicts with the execution plan, the execution plan governs; the items in §5 are the only points requiring an author decision.*
