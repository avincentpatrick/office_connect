# Module: Landing Shell & Query Bar

## 1. Status

**IN PROGRESS. Phase slot: 3 (Stage D).**

| Increment | Scope | Status |
|---|---|---|
| **D-1** | Landing shell + deterministic query bar | **✅ shipped 2026-08-06** |
| D-2 | Calendar of Activities surface — **owns its own doc, [`calendar.md`](calendar.md)** | **in progress (kickoff 2026-08-09)** |
| D-3 | CSS-IS reverse-proxied into the shell (session carries) | not started |
| D-4 | `ai_core` promoted to the shared platform AI service | not started |

## 2. Purpose

The platform's front door: React app shell (top bar, `NAV_GROUPS` navigation,
module cards) and the query bar that routes plain-language intents to modules
**and reports** ("generate CSMR", "FOI report") via `NAV_GROUPS`
`intent_keywords`. **Stage D also delivers the Calendar of Activities surface**
(owner feature 2026-07-22): a core screen reading `core_activities`, travel
claims, statutory deadlines (`core_compliance_deadlines`), and — as later
stages ship — room bookings, document deadlines, and SPMS dates; funded events
show cash-advance liquidation countdowns. Plus the promotion of CSS-IS
`ai_core` to the shared platform AI service.

## 3. Source references

- `references/OfficeConnect_Build_Execution_Plan_v1_0.docx` Phase 3
- `references/Digital_Transformation_Integration_Blueprint.md` §3/§5
- [`ui-standards.md`](../standards/ui-standards.md) — the shell is the first
  full implementation of the layout templates + token contract

## 4. Integration obligations (Blueprint §3/§5)

- Query bar routes **report intents** to the Reports/Government-Outputs screen
  (`intent_keywords` include report names + aliases).
- Shell consumes `/api/v1/config` for tenant branding tokens and feature
  flags (modules hidden when their flag is OFF).

## 5. Open decisions

- **Sequencing — RESOLVED (owner, 2026-07-22):** the shared shell + design
  tokens + component-library seed are **pulled forward into R-2**; the full
  landing/query bar stays Stage D (Phase 3). `ui-standards.md` §7 deferred
  sections fill at R-2.
- **Frontend implementation choices — RESOLVED (R-2-shell, 2026-07-28):**
  Tailwind v4 CSS-first token mapping, Lucide icons, Tailwind-default rem
  breakpoints, no Storybook. `ui-standards.md` §7.
- **Nav/permission gating — RESOLVED (D-1, 2026-08-06):** the R-2-shell deferral
  is lifted; the nav gates on permission codes from `/auth/me`. See §6a below and
  `ui-standards.md` §7.
- **Calendar surface scope detail (filters, per-role views) — RESOLVED (D-2
  kickoff, 2026-08-09).** Twelve decisions, recorded in
  [`calendar.md`](calendar.md) §5 rather than here: the Calendar earned its own
  module doc (rule 8) because later stages plug into *it*, not into the landing.

## 6. Plan

### 6a. Increment D-1 — the landing shell + query bar (shipped 2026-08-06)

**What it is.** The platform's front door. Before D-1 an authenticated user was
dropped onto a module page and `HomePage` was a placeholder. D-1 makes `/` answer
one question — *what can this person open?* — and gives them a deterministic way
to get there by typing.

**The problem that shaped it.** R-9 established that the pilot cohort **is** the
grant list (api-standards §9i): nothing in the codebase auto-assigns a role, so a
user with no grants is the *common* case, not the edge one. But the FE could not
tell who those users were — `/auth/me` returned role codes, not permissions — so
a grant-less user was shown a **Reimbursement** link that 403s on all 32 module
routes. A landing page whose whole promise is "say plainly what you can do" is
precisely the surface ui-standards §7's deferral was waiting for.

**The four kickoff decisions (owner-confirmed, 2026-08-06):**

1. **Lift the deferral.** `/auth/me` carries sorted `permissions: string[]`;
   `NAV_GROUPS` re-gates on permission codes and `requiredRoles` is deleted.
2. **The query bar lives on the landing only**, built as an inventory component
   (fully controlled, zero internal state) so it lifts into the App shell later
   without a rewrite.
3. **No match = refuse, then name everything openable.** R-9's doctrine is that a
   refusal names the surface that *does* answer the question.
4. **Pure front door.** Query bar + what you can open + a truthful no-access
   state. No counts, no dashboard, **no API calls of its own** — the page renders
   entirely from `/config` and `/auth/me`, which the shell already fetches.

**Shape.** `GET /auth/me` → `permissions` (one resolver shared with the gate) →
`visibleNavItems(features, permissions)` → `openableItems()` drops `/` → the page
hands that already-gated array to `matchNavItems()` and then to `<QueryBar>`.
Nothing downstream of the gate can widen the set.

### 6b. The query bar is NOT core-service #9 (Search) — rule 10 check

Stated plainly because the names collide and the next person will ask.
Core-service **#9 Search** (master-plan §1.1) is PostgreSQL FTS — `tsvector` +
`pg_trgm` over **records**, soft-delete- and scope-aware, with OCR text of scanned
attachments indexed. The D-1 query bar matches **labels and `intentKeywords` on
≤7 navigation destinations, in the browser, with no index, no records, no server
call and no database at all.** master-plan §1.3's connection-matrix row says it in
two words: *"routing only"*. If a later increment wants to search *records* from
the same field, that is a **consumer of #9** and a separate design — and it must
not be bolted onto this matcher.

Likewise **core-service #16 (AI service)** lists "query bar" as a consumer. D-1's
matcher is deterministic and has **no `ai_core` dependency**; #16 becomes relevant
only if a later increment adds natural-language intent. The master plan's word for
D-1 is *deterministic*, explicitly not an LLM.

### 6c. Delta register (D-1)

| # | Delta | Why |
|---|---|---|
| 1 | `MeResponse` gains **`permissions: list[str]`**, sorted | The recorded ui-standards §7 deferral, lifted. A field rather than a sibling endpoint: api-standards §1 blesses additive `v1` response fields, and a sibling adds a third boot round-trip plus a skew window where the nav renders from a permission set fetched after the roles beside it. |
| 2 | **Rejected:** snapshotting codes into the Redis `SessionRecord` at login | Stale by construction. `SessionStore.set_permissions_version` stamps the version onto live sessions but **never rewrites `roles`** — a code snapshot inherits that defect exactly, and a `valid_to` expiry would never take effect. api-standards §7 promises a grant lands on the **next request**. |
| 3 | `effective_permission_codes()` extracted in `core/auth/dependencies.py`; `require_permission` now calls it | One resolver for the gate and the "me" surface. Two readers of one set eventually disagree, and the visible form of that is a UI offering what the server refuses (api-standards §9j). |
| 4 | `sorted()` at the response boundary | `PermissionCache.get_or_load` returns a `set` on **both** the hit and miss paths, so unsorted output is non-deterministic *as a function of cache warmth* — stable in dev, arbitrary in prod. |
| 5 | `NavItem.requiredRoles` **deleted**, replaced by `requiredPermissions` (OR semantics) | Authorization is on permission strings everywhere else; the oversight items now carry `queue.OVERSIGHT_PERMS` **verbatim** rather than a three-role paraphrase; and `me.roles` was a login-time snapshot, so the old gate was not merely coarse but out of date. ui-standards §7. |
| 6 | **Consequence:** the `auditor` role loses the Reimbursement link | `ROLE_GRANTS["auditor"]` holds no `reimb.*` at all, so the link 403s today. A fix, not a regression — recorded because it will be noticed. |
| 7 | **Consequence:** a grant-less user now sees **no** module links | This is what makes the landing's no-access state real, and after R-9 it is the common case. Needs a grant-less dev account to smoke — see §6d. |
| 8 | `NavItem.description` added | The landing's muted second line comes from the nav registry, so the page has **zero hard-coded knowledge of any destination** — and it is exactly what the bar's meta line wants when it lifts into the shell. |
| 9 | **No `visibleNavGroups`** this increment | `NAV_GROUPS` has one *unlabeled* group, so a grouped render is byte-identical minus furniture. The extracted `isVisible` predicate makes it four lines the day a labelled group first exists. **Promotion trigger: Stage H's Reports items.** |
| 10 | Matcher is **generic over `{label, intentKeywords}`** and imports nothing from `nav.ts` | It structurally *cannot* acquire `NAV_GROUPS`, so it cannot offer an ungated destination — §9f's mistake foreclosed rather than merely avoided. |
| 11 | Six match tiers, ranked **exact → prefix → substring**, interleaving label and keyword | Strength of match beats which field it came from: a label and its keywords are two spellings of one destination, not two levels of authority. Empty query returns `[]`, not everything, or the results are indistinguishable from the idle page. |
| 12 | **Query bar = ui-standards §3 row 24**, a search field and explicitly **not** an ARIA combobox | Radix ships no Combobox; hand-rolling virtual focus is the hardest widget in ARIA, its 1.0→1.2 semantics changed incompatibly, and `aria-activedescendant` is unusable on iOS VoiceOver — the platform §6 prioritizes. Full reasoning in the §3 amendment. |
| 13 | **No new §4 layout template** | A template exists to enforce mandatory structure; the landing fetches nothing, so it has no loading or server-driven empty state to enforce. One consumer is not a pattern. Fill-trigger recorded in the §4 note. |
| 14 | `openableItems()` (drops `/`) lives page-side, not in the matcher | *"The front door does not list itself"* is a property of the **landing**. When the bar lifts into the App shell, `/` becomes a legitimate destination again — keeping this page-side keeps that lift clean. |
| 15 | A **nav census** ships from day one (`nav.test.ts`) | The R-9 census exists because *absence never fails a test*. The nav has the identical risk in a new substrate: an item added tomorrow with no `requiredPermissions` is silently openable by everyone. Every row must also name **the server rule it mirrors**. |
| 16 | **Deferred:** Enter-to-navigate | "Enter goes to the first result" is an invisible rule, and if the top match is wrong it moves the user somewhere they did not ask for. The narrow variant (navigate only when there is exactly one match) is ~5 lines + 2 tests if a real user asks for it. |
| 17 | **Deferred:** debounce, recent searches, hyphen folding (`per-diem`), diacritic folding | ≤7 items needs no debounce. Hyphen folding is one line in `normalize` + one test and is the first thing to add if the live smoke shows it. |
| 18 | **Deferred:** a distinct "we could not check your session" screen | `/auth/me` is no longer DB-free, so a cold cache plus a DB outage now renders as a redirect to `/login` — a blip looks like being signed out. The resolver fails as a 503 with the standard envelope (never `[]`); telling the two apart in the client is the deferred half. api-standards §9j. |

### 6d. Test posture

- **Backend** — `tests/test_auth_me_permissions.py`. The load-bearing cases:
  a grant lands on the next request **while `roles` stays unchanged** (the
  staleness fact that justifies the whole re-gate); the payload is sorted and
  equal across a cache miss and a hit; a pending session gets **real**
  permissions, not `[]`; and `test_the_me_surface_and_the_gate_agree` — the
  "never offer a button the server refuses" invariant, asserted.
- **Frontend** — `nav.test.ts` (which should have existed since R-2-shell) plus
  its census block, `nav-match.test.ts`, `landing-copy.test.ts`,
  `QueryBar.test.tsx` (including `does not use combobox semantics`, which *is*
  the inventory row's contract) and `HomePage.test.tsx` (three states, the
  duplicate-link guard, and `makes no network requests` — decision 4, pinned).
- **⚠ Live smoke needed a new dev account.** All five existing smoke accounts
  hold a role, and every seeded role carries at least `reimb.claim.read`, so
  every one of them lands in the *can-open-something* state. The no-access
  state — the common case after R-9 — was **untestable live** until
  `no-grants@doh.gov` was minted with no role at all. It must never be given a
  role "for convenience later": having none is its entire value.

### 6e. Remaining Stage D increments

D-2 Calendar of Activities — **kicked off 2026-08-09; see
[`calendar.md`](calendar.md)**, which now owns its plan, its delta register and
its test posture. Note one scope change made at that kickoff and recorded there:
**`core_compliance_deadlines` is DEFERRED** as a fourth source (the table stores
`due_rule` JSONB with 15 distinct kinds and no evaluator exists; its real consumer
is Stage H's Government Outputs). D-3 CSS-IS reverse-proxied into the shell · D-4
`ai_core` promoted to the shared AI service. Each is its own increment with its own
kickoff.

**What D-1 leaves ready for them:** every new surface is one `NAV_GROUPS` row —
gated, matchable and listed on the landing the moment it is added, with the census
failing the suite if that row ships without a declared rule.
