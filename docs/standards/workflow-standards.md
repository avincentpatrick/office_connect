# Workflow Engine Standard

Binding conventions for the **one** shared approval/routing engine
(`core_workflow_*`, `office_connect/core/workflow/`). Rule 10 + master-plan §1.1 #1:
every approval/routing flow platform-wide — reimbursement, DTWIS routing, QMS DCRs,
supply requisitions, PPMP/WFP, SPMS — runs on this engine. **No module builds its own
approval machinery.** Shipped Stage C (migration `0012`); reimbursement is the first
consumer (its chain becomes the engine's first *definition* at R-4-app).

Precedence: this doc is the authoritative operational contract; the design basis is
[`docs/research/round1/approval-workflow-engine-design.md`](../research/round1/approval-workflow-engine-design.md)
and master-plan §1.1 #1.

---

## 1. State machine as data (three separated concerns)

- **Design-time** (versioned, immutable once published): `core_workflow_definitions`
  → `core_workflow_definition_versions` → `core_workflow_states` +
  `core_workflow_transitions`.
- **Runtime** (small, hot, mutable): `core_workflow_instances` (pinned to a version;
  carries the CAS `row_version`, `revision_no`, and the guard inputs `amount`/`context`)
  + `core_workflow_steps` (per-approver fan-in rows, scoped to `revision_no`).
- **History** (append-only, immutable): `core_workflow_events` — the authoritative
  decision log. `current_state_id` on the instance is a **derived read-model**;
  `core/workflow/replay.py::fold_events` reproduces it (a QA-gate consistency test).

A status column mutated by scattered code is forbidden — legality is a closed,
queryable transitions set.

## 2. Typed guards, never a DSL

Routing branches on **typed columns** only: `min_amount`/`max_amount` (the instance's
`amount` routes), plus `required_permission` and `requires_comment`. When several
transitions share `(from_state, action)`, the first whose guard passes — by
`sort_order` — fires. An unbounded expression language is an unauditable security
surface; add a typed column when a real rule appears, never a DSL.

## 3. Authorization is server-side, on permission STRINGS

Authority is resolved by `core/org_units.py::authorize_scoped` (never role names in
code). Gate actions (approve/return/reject) authorize against the active step's
`required_permission` at the step's org unit; originator actions (submit/resubmit/
cancel) authorize by ownership or the transition's permission. `available_actions`
computes the (state × actor × guards × delegation) set the UI renders AND the POST
re-validates through `execute_action` — the UI never computes permissions itself.

**Segregation of duties** (`enforce_segregation` on a gate state) calls
`core/maker_checker.py::assert_segregation` — no self-approval, distinct approver per
slot (four-eyes). COA 92-389 / NGICS.

**`available_actions` must not offer an action that is certain to fail**
(R-4-screens, 2026-08-03). Because the UI is forbidden from computing
permissions, an action in that list is a promise: `execute_action` would accept
it, for this actor, now. So the ACTOR-dependent gate guards are mirrored into
the `approve` branch — the actor already holds a `done` slot of this gate
(`workflow_step_already_acted`), and the actor is the instance originator under
`enforce_segregation` (`segregation_of_duties`). Before this, a chief who filed
their own claim was shown an Approve button that always 409'd. Race-driven 409s
remain normal and expected (someone else acted first); a *predictable* 409 is a
bug. The guards themselves stay in `execute_action` — this is a filter, not the
enforcement.

## 4. Every transition is atomic, idempotent, concurrency-safe

`execute_action` runs ONE transaction: `SELECT … FOR UPDATE` the instance → idempotency
replay (unique `(instance_id, idempotency_key)`) → CAS (`expected_version` mismatch or a
terminal state → **409**) → route → authorize → step fan-in (`SELECT … FOR UPDATE`,
`join_type` all/any/quorum over the current revision's live steps) → advance
`current_state` + bump `row_version` → append the event. Because the audit chain forbids
unaudited bulk DML, the CAS is a row lock + in-Python check + an audited ORM mutate — not
a raw conditional `UPDATE`; correctness is identical, auditability preserved.

Error codes (structured `APIError`): `stale_workflow_version`, `workflow_state_conflict`,
`workflow_step_already_acted`, `workflow_not_authorized`, `workflow_transition_not_allowed`,
`workflow_comment_required`, `segregation_of_duties`, `workflow_module_disabled`,
`workflow_definition_not_published`, `workflow_version_published`, `workflow_invalid_definition`.

## 5. Versioned, immutable definitions

Editing a chain creates a NEW version; publishing validates the graph (exactly one
initial state, ≥1 terminal, every non-terminal has an exit, all states reachable) and
freezes it (a published version cannot be edited). New instances start on the **latest
published** version; in-flight instances stay pinned to theirs and finish on them.

## 6. Return vs Reject; revision tracking

`return` loops back to a person (holder = originator) and requires a comment; `resubmit`
re-enters the chain and bumps `instance.revision_no` (fresh steps, fanned in
independently of the prior visit's — signatures bind to the current revision). `reject`
is terminal. Every prior decision stays in `core_workflow_events` across revisions.

## 7. Delegation / OIC — on-behalf-of

`core_workflow_delegations` (delegator → delegate, optional definition/org scope, time
window) grants a person the authority to act for another. `execute_action` records BOTH
`actor_user_id` and `on_behalf_of_user_id`, so the trail reads "Approved by Cruz (OIC for
Reyes)". This **refines** the Stage-B B3 "no RBAC delegation table" decision — a
role-window grants a ROLE; a delegation records one PERSON exercising another's authority
for a workflow action (a concept role-windows cannot express). See `foundation.md` §7.

## 8. SLA — idempotent, non-interrupting

Steps get `sla_due_at` at activation (from the gate state's `sla_hours`). The Celery beat
`ops.sweep_workflow_sla` calls `core/workflow/sla.py::sweep_due_steps`, which appends one
`escalation` event per overdue step (`SELECT … FOR UPDATE SKIP LOCKED`; partial-unique
`(step_id, escalation_level)` guards at-least-once double-fire) **without** moving the
step or instance. The engine escalates once; **delivery + the recurring ladder are the
consuming module's** (delivered for reimbursement at R-4-app, 2026-07-29):
`ops/reimbursement_tasks.py` registers the notifier via `register_sla_enqueuer` (the
ops→core seam — NOTE: the enqueuer fires after flush INSIDE the sweep transaction,
before commit, so the enqueued task must re-read committed state defensively) and runs
the repeating working-day ladder as its own beat task (`ops.reimb_sla_reminders`),
idempotent via notification-outbox dedup keys. Working-day due dates are stamped by the
module wrapper (gate states authored `sla_hours=None`; the engine column is calendar
hours) until the holiday-calendar core service (#6) grows an engine-side seam.
Escalation is a nudge to the holder — superiors are never auto-rerouted
(work-management non-negotiable: holder-only SLA ladder).

## 9. Feature-flag semantics

`start_instance(feature_flag_key=…)` blocks a NEW instance unless the flag is ON
(`enabled AND is_active`, the `/api/v1/config` rule). `execute_action` **never** reads the
flag → in-flight items always finish. Turning a module OFF stops new work; it never
strands work in progress.

**The HTTP surface must mirror this** (R-4-screens): a module's action POSTs
live on a separate, un-gated router so an approver can still clear an in-flight
item with the module switched off. Everything else stays behind the 404 gate.
The full pattern, and the reasoning for where the line falls, is
api-standards §9a.

## 10. Purity & the polymorphic back-ref

`core/workflow/` imports only `core.*` — no module tables. A module's business row FKs
INTO `core_workflow_instances` (`<x>.workflow_instance_id`); the instance references the
business row only via the sanctioned polymorphic `(subject_kind, subject_id)` with **no
FK** (database-standards §3). The SLA Celery task lives in `ops/` and injects via the
seam, keeping core worker-free (`lint-imports` stays green).

## 11. `core_workflow_events` — audited append-only

`created_*` only + `REVOKE UPDATE FROM oc_app`, but **NOT** in
`core/audit.py::_UNAUDITED` — so every event INSERT hash-chains into `core_audit_logs`
(the log rides the same integrity proof as the business tables). Its free-text/SPI
`payload` is `__audit_exclude__` (value withheld from the chain, field name kept);
`comment` is kept in clear — it is the decision rationale COA needs.

## 12. A decision that records DATA is a separate, prior service call

`execute_action` takes an actor, a comment and a CAS token. It does **not** take a
payload, and it must not grow one. A transition whose meaning depends on figures — a
settlement, a disbursement, a receipt number — is therefore **two calls in one
transaction**: a module service records the data, then drives the ordinary verb.

```
record_x(session, …)        # writes the facts, flushes
  → lifecycle.claim_action(action="approve", …)   # the unchanged engine verb
```

Three rules make that safe, and all three are load-bearing:

1. **One transaction, always.** The data write and the transition commit together or
   not at all. Split across two requests, the first one's side effects (a released
   lock, a freed slot, a notified party) stand alone with nothing to complete them,
   and this platform has no compensating-transaction machinery to undo them.
2. **The data write goes FIRST.** It must not touch `instance.row_version`, so the
   CAS token the client read is still the token at transition time. Reversed, a
   caller could pass a stale version and have the data recorded against a transition
   the engine then refused.
3. **The gate refuses the bare verb.** The module adds a precondition at that state —
   *the data must already be there* — so the generic action route cannot reach the
   state that asserts it. The refusal NAMES the route that does the thing (§9.1
   principle 4); a bare "not allowed" leaves an operator holding a button that always
   fails.

The client-facing verb is then **rewritten, not dropped**: the actor is authorized to
clear that gate, so `available_actions` offers the verb that WORKS (`settle` in place
of `approve`) rather than leaving a hole where the button belongs.

Instances so far, both in reimbursement:

| Chain | Terminal state | Data it must record | Service | Client verb |
|---|---|---|---|---|
| `reimbursement.liquidation` | `settled` | refund OR / settlement mode, on the advance | `services/settlement.py::record_settlement` (R-6-liq-settle) | `settle` |
| `reimbursement.claim` | `paid_closed` | the payment reference + date FMS gave back | `services/external.py::record_payout` (R-7-events) | `mark_paid` |

The second one is the useful evidence: the pattern held with **no amendment to this
section**, and the only new advice it produced is about the *rewrite table*. When a
module has two chains, keep the state→verb mapping in ONE kind-keyed structure rather
than two `if` branches — two chains answering the same question in two places is how
they drift on the day a third arrives.

Widening `execute_action` instead would have put one module's money on every future
module's transition.
