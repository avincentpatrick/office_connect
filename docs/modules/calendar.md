# Module: Calendar of Activities

## 1. Status

**COMPLETE on its shipped scope. Phase slot: 3 (Stage D Increment 2).**
Owner-requested feature, recorded 2026-07-22. Kickoff 2026-08-09; shipped
2026-08-09; through the Stage D QA gate at `0.4.0` / `stage-d-complete`.

| Increment | Scope | Status |
|---|---|---|
| **D-2** | The agenda surface: activities + travel + liquidation clocks | **✅ shipped 2026-08-09** |
| — | Statutory deadlines as a fourth source | deferred (see §5a) — an occurrence engine, and Stage H's consumer |
| — | Room bookings · document deadlines · SPMS dates | arrive with their modules, one file + one line each (§6b) |

## 2. Purpose

The answer to **"what is happening, and what is due?"** — and the first surface to
make `core_activities` do the job the master plan gives it. §1.2 calls that table
**the connection spine**: *"the answer to 'what work was this for?'. Everything links
to it."* Until D-2, nothing did — the table had a model, four FK holders and **no
read surface at all**: no endpoint, no service, no permission.

The consequence was concrete and recorded elsewhere before it was fixed here.
[`reimbursement.md`](reimbursement.md) delta row for spec §9.3 step 1 says the
wizard's activity picker was *"omitted from v1 — no activities HTTP endpoint exists
yet"*, and the live database agreed: **0 of 838 claims carried an `activity_id`.**
The spine was a column nobody could fill because nobody could browse it.

## 3. Source references

- [`master-plan.md`](../master-plan.md) §1.2 (the connection spine), §1.3 (the
  `reimb → calendar` row: *"CA `date_return` → liquidation countdown on linked
  event"*), Stage D
- [`landing.md`](landing.md) §6e — D-2 is one of Stage D's four increments
- `references/Digital_Transformation_Integration_Blueprint.md` §2.2 / §5

## 4. Integration obligations

- Reads the spine (`core_activities`) and every module that points at it.
- Working-day and holiday math **only** through `core/workdays.py` (core-service
  #6, rule 10). A calendar that does its own date math is precisely the
  duplication rule 10 exists to stop.
- Liquidation urgency comes from `modules/reimbursement/services/deadline.py` —
  the engine that already owns the COA 97-002 clock.
- One `NAV_GROUPS` row makes it matchable in the query bar and listed on the
  landing (D-1's hand-off).

## 5. Kickoff decisions (owner-confirmed, 2026-08-09)

| # | Decision | Why |
|---|---|---|
| 1 | **Reset the dev DB before any feature work** | The suite was failing a different set on each run, including at a commit D-1 never touched. See §6a. |
| 2 | **Activities tenant-wide; travel bounded by `oversight_scope` ∪ your own** | api-standards §9h — for an aggregate the scope IS the privacy boundary. Activities are organisational work; travel carries destinations, purposes and peso totals. |
| 3 | **An agenda list, not a month grid** | ui-standards §6 is phone-first, and a table of days is the classic screen-reader trap. No new §4 template — see the 2026-08-09 template note. |
| 4 | **Three sources; statutory deadlines deferred** | See §5a. |
| 5 | **A `CalendarSource` registry in core, filled at the composition root** | The import-linter contracts make the module's scope rule unreachable from any calendar package. api-standards **§9k**. |
| 6 | **Richer relative-dated demo fixtures; no write path** | The master plan's word for this surface is *reads*. A create/edit screen is its own increment with its own workflow and audit questions. |
| 7 | **A new `activity.calendar.read` permission, granted to all five seeded roles** | `activity.read` / `activity.manage` are reserved for a future registry-maintenance screen, so the calendar's grant can never quietly become the registry's edit grant. |
| 8 | **No calendar strip on the landing** | D-1 shipped the anti-dashboard deliberately and pins it with `stubFetch({})`. The calendar is one nav row; the landing needs no edit at all. |
| 9 | **State the RULE, never a count of hidden rows** | "3 more you cannot see" is a disclosure the actor could not assemble by hand. api-standards §9k. |
| 10 | **Its own module doc** (this file) | Rule 8. Later stages plug into the Calendar, not into the landing. |
| 11 | **The liquidation layer is OWN ADVANCES ONLY** | See §6b — this is a correction, not a scope cut. |
| 12 | **Tenant-wide activities are genuinely tenant-wide** | Acknowledged on the record rather than left implicit. See §6c. |

### 5a. Why statutory deadlines are deferred

`core_compliance_deadlines` **has no due-date column.** It stores `cadence` +
`due_rule` JSONB + `use_working_day_math`, effective-dated. Putting it on a calendar
means building an *occurrence expander*, and the live table showed **15 distinct
`due_rule.kind` values** across 22 seeded rows:

`fixed_date` · `fixed_month` · `fixed_dates` · `semiannual` · `quarterly_plus_annual_summary` ·
`days_after_quarter` · `day_of_following_month` · `days_after_year_end` ·
`working_days_from_event` · `days_from_event` · `before_expiry` · `date_ladder` ·
`every_n_years` · `per_certification_body` · `per_item_checklist`

Several **cannot be expanded at all** without inputs no table supplies today (an
event date, a certification body's schedule, an expiry). Shipping the five
deterministic kinds and silently dropping the rest would be a calendar that looks
complete and is not — §9f's failure mode. And the expander's real consumer is Stage
H's Government Outputs countdown cards ([`reports.md`](reports.md) §2), which is
where it should be designed. **Fill-trigger:** the Government Outputs surface, or a
user asking for a statutory deadline on the calendar — whichever comes first.

## 6. Plan

### 6a. The reset, and what it exposed

Three full suite runs at #29 each failed a *different* set. The diagnosis was shared
state surviving across tests, and the reset was the owner's call. Two findings from
the live database made the case, and one of them is new:

| Table | Rows before the reset |
|---|---|
| `core_users` | 30,493 |
| `core_audit_logs` | 568,461 |
| `core_compliance_deadlines` | **70 — of which 48 were leaked `csmr_to_arta_<hash>` test rows** against 22 real seeds |
| `core_activities` | 473 (288 live), including rows titled "Tamper target" and "Chain test" |

**`seed_guard` cannot see this class of leak, and that is worth stating plainly.**
It snapshots the rows each dataset *declares* and diffs them before and after the
run — so it catches a seeded row that was **modified** and not restored, which is
exactly the job it was built for (#28). Rows **added** under fresh natural keys are
invisible to it. Forty-eight hash-suffixed deadline rows in a seeded reference table
are what that blind spot looks like.

> **✅ Closed at the Stage D gate (#32) by `seed_addition_guard`** —
> `tests/conftest.py`, a sibling to `seed_guard` rather than a change to it, because
> mutation and accumulation are different diagnoses and a failure message should
> mean one thing. It diffs the live natural-KEY SET of all 13 seeded tables around
> the session and fails the run on any growth, naming the table and the added keys.
>
> **It was made to fire before it was made to pass**, and on its first run it named
> four tables, not one: `core_compliance_deadlines` (the row above),
> `core_holidays`, `core_pap_codes` and `core_object_codes`. Fixed by
> `owned_row(session, row)` — the `_holiday()` shape promoted to conftest and
> applied across `test_calendar_workdays.py`, `test_uacs_codes.py` and
> `test_activity_tags.py`: soft delete in a `finally`, so a failing assertion cannot
> skip the undo, and the partial-unique indexes free the key again. A fifth leak was
> **latent in conftest itself** — `make_user` mints a `core_roles` row for any code
> outside the seeded five, and only survived because every caller happens to name
> one of the five.
>
> **The exemption list ships empty and should stay that way.** A seeded reference
> table is config, not scratch space; `seed_guard`'s own docstring used to call
> these rows "ordinary test data, not seed drift", and the 48 rows above are the
> counter-evidence. Both docstrings now say so and point at each other.

**⚠ And the reset destroyed five accounts no code could recreate.** PROGRESS.md
described the six-account smoke cohort in prose, but only `no-grants@doh.gov` was
reproducible — added to `bootstrap` at #29 precisely because someone had hit this
wall once already. The other five had been minted by hand in earlier sessions. They
are now `_SMOKE_ORG_UNITS` / `_SMOKE_STAFF` / `_SMOKE_ACCOUNTS` +
`_ensure_smoke_cohort()` in `ops/bootstrap.py`, created idempotently by
`load-fixtures`. **A cohort described in a document is not a cohort** — the same
lesson `_backdated` learned about docstrings that ask callers to clean up after
themselves.

The smoke tree is deliberately separate from the BLHSD fixture tree, because smoke
asserts that a scoped officer in one office cannot see another office's work, and
that needs two offices which genuinely do not contain one another:

```
SMOKE-A  (office)          SMOKE-B  (office)   ← scoped-officer@doh.gov granted HERE
└── SMOKE-A1 (division)    └── SMOKE-B1 (division)
    └── SMK-A-1                └── SMK-B-1
        board-traveller            smoke-b-traveller (the stranger)
    smoke-approver-a
    granted on A1
```

The scoped officer is granted on the **office** while the staff sit in the
**division** below it — on purpose, so the smoke exercises
`descendants_or_self` rather than an equality on one unit.

### 6b. The three sources

| Key | Flag | Scope rule | Notes |
|---|---|---|---|
| `core.activity` | none | **tenant-wide** (decision 12) | `division_id` / `section_id` exist on the row and are deliberately **not** filtered on. `href = None` — an inert row, no detail screen exists. **`Activity.custom` never crosses the wire** (see §6c). |
| `reimb.travel` | `module.reimbursement` | `queue.oversight_scope` + `queue.base_query(include_terminal=True)`, unioned with own claims by `claimant_id` | `include_terminal=True` because a trip that already happened and was paid is still a calendar fact — the queue excludes terminals because it is a *work* queue, which is a different question. The own-claims branch has no `WorkflowInstance` join, so **your draft trip shows on your own calendar**: an unsubmitted trip is still a trip you are taking. |
| `reimb.liquidation` | `module.reimbursement` | **own advances only** (decision 11) | See below. |

**Why the liquidation layer feeds the ADVANCE and not the claim.**
`reimb_claims.liquidation_deadline` looks like the obvious source and is the wrong
one: `services/cash_advance.py::link_claim` calls it *"a MIRROR, written here only"*,
re-pushed by `remirror_deadline`, with `reimb_cash_advances.deadline_date` as the
source of truth. Feeding both would put **two countdown rows for one obligation on
the same day** — a defect that looks exactly like working software. The linked
liquidation claim is read only to enrich `href` and `status_label`, which is what
`cash_advance_out` already does.

**Why own-advances-only, and what it would cost to widen.** There is **no set-form
scope rule for cash advances anywhere in the codebase**: `GET /cash-advances` is
single-claimant, and `deps.can_read_cash_advance` is a per-row rule that places a
person by `staff.section_id or staff.division_id` — a *different* placement rule
from the claim's `WorkflowInstance.org_unit_id`. Building the set form means writing
a second org-placement predicate for the same module that must agree with the first
one forever, which is the exact drift hazard `base_query`'s own docstring warns
about; and it would disclose "person X took a cash advance" in a list where that has
never been visible. Own-only delivers the COA 97-002 clock in full to the person the
clock is about. **Cost to widen later:** one service function, two census rows,
three security tests.

Also: the liquidation row carries **no peso amount and no DV number**. The calendar
has no business carrying financial identifiers.

### 6c. Two exposures acknowledged rather than discovered

1. **Tenant-wide means tenant-wide.** `core_activities.title` is free text somebody
   typed. An activity titled *"Disciplinary hearing — J. Cruz"* becomes bureau-public
   the moment this ships. The owner acknowledged this deliberately (decision 12): the
   spine only works as a join key if everyone can see it. **Fill-trigger for a real
   change:** a `visibility` column on `core_activities`, the day the answer differs.
2. **`Activity.custom` is free JSONB on a tenant-wide surface**, so it is excluded
   from the wire by construction and pinned by a test. A tenant can put anything in
   it, including the thing rule 1 is about.

### 6d. Delta register

| # | Delta | Why |
|---|---|---|
| 1 | **api-standards §9k** — a surface composed of sources that cannot see each other | The first endpoint whose content comes from more than one module. |
| 2 | `CalendarSource` is a **frozen dataclass, not a Protocol** | A protocol needing both `__call__` and `key`/`label`/`feature_flag` forces every implementation into a class or a function with bolted-on attributes. A dataclass is **introspectable**, which is what makes the source census possible. |
| 3 | `register_source()` is **idempotent by construction** — a dict keyed on `key`, not a list | `tests/` import `office_connect.main`, repeatedly. A list would double every event the second time a test module imported it. Idempotence by discipline is not idempotence. |
| 4 | `registered_sources()` returns **key-sorted** | Same reasoning as D-1's `sorted()` on `/auth/me`: an order that depends on import order is non-deterministic as a function of *how the app was loaded*, stable in dev and arbitrary elsewhere. |
| 5 | `scope_rule` is **required**, and `register_source` **raises** on an empty one | R-9's census lesson in a third substrate. A source with no declared rule is how a calendar leaks, and absence never fails a test unless you make it. |
| 6 | The **feature flag rides the source**, not the route | A core route cannot be per-module gated. A flag-OFF source is **absent** from `sources[]`, not present-and-empty — an empty `reimb.travel` block would announce a module the tenant has not bought. |
| 7 | **No `limit` / `offset`** — the window is the paging control | §9g's board precedent, plus a correctness reason: past a per-source cap, an offset drops rows from the **middle** of the merged chronology while `total` still looks right. |
| 8 | `bounded_note` is a **sentence, never a hidden-row count** | Decision 9. A count of rows you cannot read is a disclosure you could not assemble by hand. |
| 9 | Empty days are **omitted** from the response | An agenda is a list of days that have something. 92 empty rows is a month grid wearing a list's markup. |
| 10 | `today` rides the envelope | So the page's "Today" divider is the **server's** Manila day, not the browser's — the same reasoning `CountdownRing` already applies to `days_remaining`. |
| 11 | **No new §3 component**; `WorkItemRow` left alone | Its `to` is required and its identity is "linked ref + title". Widening a contract for one consumer weakens it for the six that rely on it. Page-local composition, per the R-5 `GeneratedDocCard` doctrine. |
| 12 | Migration `0024` — `ix_reimb_claims_date_depart` | The travel source's window predicate. `core_activities` and `reimb_cash_advances` already had theirs; this one was missing. |
| 13 | `core/features.py::feature_enabled` **extracted** from `require_feature` | Rule 10: one reader of `core_feature_flags`. The dispatcher needs the same test the route gate applies. |
| 14 | `core/workdays.py` gains `load_nonworking_labels` | Rule 10: one reader of `core_holidays`. The agenda names the holiday rather than merely greying the day. |
| 15 | The smoke cohort becomes **reproducible** (`_ensure_smoke_cohort`) | §6a. The reset destroyed five accounts no code could recreate. |
| 16 | **Deferred:** statutory deadlines | §5a — 15 `due_rule` kinds, no evaluator, several unexpandable; the real consumer is Stage H. |
| 17 | **Deferred:** an activity write path, and reimbursement's wizard activity picker | Both now *unblocked* by this endpoint. Recorded so the next session knows the door is open. |
| 18 | **Deferred:** a month grid | Fill-trigger: a user asking to see a whole month at once. |

### 6e. Test posture

**The census gap is the load-bearing part.** `tests/test_reimb_authz_census.py`
filters routes on the `/api/v1/reimbursement` prefix and
`tests/test_reimb_scope_security.py` asserts `len(oversight_paths) == 3`. The
calendar's travel source is a **fourth consumer of `oversight_scope`** living outside
that prefix — so **both tests stay green whatever the calendar does**. Three
deliverables close it: `tests/test_calendar_sources.py` (a *source* census, the third
instance of the R-9 pattern after `AUTHZ_TABLE` and `NAV_CENSUS`), two new
attacker-shaped tests inside `test_reimb_scope_security.py` where the other chairs
already live, and an amended drift message pointing at the new file.

**The clock.** There is no `freezegun` in this repo, by convention: services take an
injected `now`/`today` and HTTP tests move the *data*. A calendar is that problem in
its purest form, and it has an advantage the queue never had — **`?start=&end=` IS
the seam `_backdated` was faking.** `holder_since` is compared against `utc_now()`
inside the service with no way to ask a different question, which is why that helper
had to own its undo; here a test creates a row in a private year and asks for that
year's window. Absolute assertions are safe, nothing shared is mutated, nothing needs
undoing. Convention: each calendar HTTP test module claims `_ISOLATED_YEAR = 2029`,
outside every fixture's range.

`urgency` is the one thing a window cannot isolate — it is relative to *today*, not
to the requested window. It is computed by the already-exhaustively-tested pure
`deadline.deadline_state(deadline=…, today=…)` and asserted over HTTP only as a
**shape**. Rejected: a `?today=` debug parameter — a client-controlled clock on a
surface whose whole job is stating deadlines is the same class of mistake as
client-side money.

## 7. Manual test guide

Plain-language, driven in a browser at `http://localhost:5174`. All dev logins
use `BoardSmoke!2026x`. Prepare with `bootstrap load-fixtures` +
`load-pilot-fixtures` + `set-flag module.reimbursement --on`.

**1. It is listed, and it is findable.** Sign in as `board-traveller@doh.gov`.
The landing lists **Calendar**. Type "when" or "schedule" in the query bar —
Calendar appears. (Neither is its label: both are `intentKeywords`.)

**2. It opens on what is coming up.** Open Calendar. The list starts at today,
grouped by date, most recent first. Each day shows its date as a heading and the
things on it underneath. **Days with nothing on them are not listed** — scroll
and you should never see an empty date.

**3. Every status tone is visible.** The fixture activities are dated relative
to the day you loaded them, so you should see a mix: a grey "Planned", an amber
"Ongoing", a green "Done" in the past window, and a red "Cancelled". Switch
**Show** to "Last 30 days" and the past ones appear.

**4. It tells you what you are not seeing.** As `board-traveller`, below the
list: *"Travel shown here is your own. Colleagues' claims are not on this
calendar."* That sentence must be there **even when the calendar is empty** —
switch to a window with nothing in it and confirm it stays. **It must never say
how many rows are hidden.**

**5. The scope is real, from two chairs.** File and submit a claim as
`board-traveller` (their staff row sits in Smoke Division A1). Then:
- `smoke-approver-a@doh.gov` (approver on A1) sees the trip on their calendar.
- `scoped-officer@doh.gov` (Smoke Office B) sees **the same activities** and
  **not** the trip.
- `smoke-b-traveller@doh.gov` sees neither the trip nor any travel at all.
That difference — same activities, different travel — is the whole design.

**6. Your own clock, and only yours.** Record a cash advance for
`board-traveller` as an Admin Officer, with a return date ~25 days ago. On
`board-traveller`'s calendar, a **Liquidation due** row appears on the deadline
date, amber or red. On the Admin Officer's own calendar it does **not** appear —
liquidation clocks are the claimant's. Confirm the row shows **no peso amount
and no DV number**.

**7. A window you cannot over-ask.** Edit the URL to
`/calendar` and pick "Next 90 days". Everything still loads. (The server caps a
window at 92 days and says so when it clamps; the picker never offers more.)

**8. Nobody sees a calendar they are not entitled to.** Sign in as
`no-grants@doh.gov`. The landing shows **no Calendar link**. Go to `/calendar`
directly: the page renders **the server's own refusal sentence**, not a blank
list — an admin surface is reachable by anyone and refused by the server.

**9. A switched-off module leaves no trace.** Run
`bootstrap set-flag module.reimbursement --off`, wait ~30 s (the `/config` cache
TTL), and reload the calendar as `board-traveller`. Activities are still there;
the travel and liquidation sections are **gone entirely** — not present and
empty. Switch it back on afterwards.
