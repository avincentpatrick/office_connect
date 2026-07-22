# Office-Connect — Phased Rollout Assessment

**Companion to:** `OfficeConnect_Build_Execution_Plan_v1_0.docx` (v1.0, the single source of truth)
**Question assessed:** *Can we do a phase-by-phase rollout of features, starting with travel reimbursement?*
**Purpose:** Pressure-test the idea before building. This document does **not** change any locked decision in the execution plan; it assesses feasibility and proposes plan enhancements for the author to accept or reject. If any fact here conflicts with the execution plan, the execution plan governs.

---

## 0. Short Answer

- **Phase-by-phase feature rollout is feasible and, in fact, is already the plan's DNA** — but the plan phases the *build*, not the *release to users*. It ships to users at only two moments: an early pilot at the end of Phase 7 (Q7) and bureau-wide after Phase 10 (§26). Turning that into a continuous, feature-by-feature drip to users is a supported enhancement, not a rewrite.
- **Nothing can be literally "first," including travel reimbursement.** There is an irreducible *foundation floor* — Phases 0–2 plus the DOH governance gate — beneath any user-facing feature. This floor is a hard constraint of the plan's own locked decisions (one login C-3, hosting/backup/audit/theming Phase 0), not a matter of preference.
- **Travel reimbursement is currently out of scope and unspecified.** It appears only in the grounding companion (§3.6) as a future FMS-family capability, explicitly "not in the first build." Choosing it as the first *module* is viable on top of the floor, but it (a) needs a dedicated requirements session first — the same gate the plan already applies to WFP (Q6, §22) — and (b) trades away the plan's core de-risking logic, which is to start from the two assets that already exist (live CSS-IS, DMWIS spec'd to v5.4).
- **Recommendation:** Adopt an explicit **two-track model** (Build Track + Rollout Track), keep Phases 0–2 as the non-negotiable floor, and treat travel reimbursement as a **scoped new module released behind a feature flag** — not as a reason to displace the CSS-IS/DMWIS critical path. Decide the sequencing trade-off (§7) deliberately rather than by default.

---

## 0.1 Decision Record (author, this round — supersedes the open recommendation below)

The author reviewed this assessment and **decided to lead with Travel Reimbursement (Local) as the first user-facing module**, on top of the non-negotiable foundation floor. The two-track model (§6) and the foundation floor (§3) are adopted as written; the open sequencing trade-off (§7) is now **resolved in favour of reimbursement-first**, and the "keep DMWIS/CSS-IS first" default in §7 no longer applies. The dependency analysis, build sequence, and grounded requirements live in the dedicated handoff: **`Reimbursement_First_Dependency_Analysis.md`**.

| Decision | Value |
|---|---|
| First user-facing module | **Local travel reimbursement + local cash-advance liquidation** (foreign parked) |
| Build approach | **Standalone module** on the floor, reconciled with DMWIS later (over shared-kernel-first) |
| Requirements gate | **Yes** — a scoping session (R-0) before build, per the WFP gate (Q6/§22) |
| Pilot cohort | **Finance/Admin unit + a few frequent travellers**, behind a feature flag |
| Module objectives | Automate the documentary requirements · check documents against the `FS-BD-01` standard · learn from recurring reviewer comments · monitor reimbursement progress |

The §5 feasibility table's recommended path ("early standalone module on the floor") is the one selected — with the author accepting the standalone build's reconciliation debt (managed via module-internal service seams; see the handoff). §8's enhancement to register reimbursement in §22 is now moot: it is an active first module, not a parked candidate.

---

## 1. Two Different Things Called "Phased Rollout"

The request collapses two distinct ideas. Separating them resolves most of the question.

| | **Build phasing** (constructing the system) | **Rollout phasing** (releasing to users) |
|---|---|---|
| In the plan today? | **Yes, fully.** 11 phases (0–10), each a complete testable unit with automated QA + author manual test before the next begins (§23, §25). | **Partially.** Two release events only: early pilot at end of Phase 7 (Q7) → bureau-wide after Phase 10 (§26). Not a continuous feature drip. |
| What the request wants | Already satisfied. | This is the real ask: hand users functional slices incrementally. |

So the honest framing is: *the plan already builds in phases; the enhancement is to also **release** in phases.* That is the lens for the rest of this assessment.

---

## 2. Does the Architecture Support Incremental Feature Release?

**Yes — decisively.** The plan was designed for exactly this, largely to serve the multi-tenant commitment (§4). The same mechanisms that turn modules on/off per agency also turn them on/off per rollout stage:

| Mechanism | Plan reference | Why it enables staged release |
|---|---|---|
| Database-driven feature flags, cached in Redis, **fail-safe OFF** | Q12; Day-1 item 9 | A half-built feature stays dark until flipped on. "Never leak to staff" is already the default. |
| Per-tenant module toggles ("feature flags, not feature removal") | Decision 19; §4 | Modules ship in the codebase but are invisible until enabled — release ≠ deploy. |
| Monorepo with enforced module boundaries (import-linter) | Q11; Day-1 item 7 | A new module is added without destabilising others; no cross-module coupling to unwind. |
| Per-module reference-number namespaces | S-4; Day-1 item 12 | A new module mints its own sequence with zero collision risk against CSS-IS/DMWIS. |
| `NAV_GROUPS` with `required_module` + `required_roles` | Q13; S-6 | Nav and query bar render only enabled, permitted items from one source — no drift when a feature appears or disappears. |

**Conclusion:** incremental, feature-by-feature release to user cohorts is not a stretch for this architecture — it is the grain of it.

---

## 3. The Foundation Floor — What Nothing Can Precede

Incremental release has a floor. These are prerequisites for *any* user-facing feature and follow from the plan's own locked decisions, so they cannot be skipped to "get to reimbursement faster":

1. **Phase 0 — Foundation.** Hosting (HF Docker Space + persistent-storage Postgres), the deploy/backup discipline with a proven restore, append-only hash-chained audit, timezone correctness (UTC store / Manila display), theming tokens, and the `/api/v1/config` feature-flag contract. Everything hangs on this skeleton.
2. **Phase 2 — Shared core auth/RBAC/directory.** The "one login" promise (C-3) means **no user-facing feature may precede unified identity**. A reimbursement flow is signatory-bound and user-scoped — it is meaningless without accounts, roles, and the staff directory.
3. **Governance gate (§24 #6).** DOH hosting clearance under the Data Privacy Act is a binding pre-flight gate. Reimbursement carries **financial + personal data**, so this gate applies with at least as much force as it does to documents.

Phase 1 (CSS-IS → PostgreSQL migration) is on the critical path only because Phase 2's shared auth is *promoted from CSS-IS's already-migrated data* (C-3). If — and only if — reimbursement genuinely displaced CSS-IS as the first user-facing module, Phase 1 could in principle be deferred; but that would forfeit the plan's single biggest de-risking move (§7).

**Net:** the earliest any new feature — reimbursement included — can reach a user is *after* Phases 0 and 2. "Start with travel reimbursement" means "start with reimbursement as the first module on the floor," not "start with reimbursement on day one."

---

## 4. Travel Reimbursement Specifically — Where It Stands Today

- **It is not scoped.** The execution plan never lists reimbursement as a module, phase, or feature. Its only appearance is the grounding companion §3.6, describing FMS documentary-requirement checklists (Local/Foreign Travel reimbursement & liquidation; Itinerary Appendix A; Certificate of Travel Completed Appendix B; Certificate of Appearance) as "**not in the first build**" — evidence of the *kind* of process the platform will eventually absorb, nothing more.
- **Its shape overlaps heavily with DMWIS.** Reimbursement is checklist-driven, signatory-bound, deadline-bearing, and audit-critical. The machinery it needs is largely what DMWIS Phases 4–7 build:
  - approval/routing chains → Phase 5 (routing, assignment, sub-tasks);
  - digital signatures via frozen PDF snapshot + SHA-256 → Phase 6 (§19.8, Day-1 item 14);
  - working-day deadline computation with a holiday calendar → Phase 7;
  - tamper-evident audit → Phase 0 core.
  - Building reimbursement *before* DMWIS therefore means either **building that machinery in its future home** and having reimbursement consume it, or **duplicating it** and paying to reconcile later. The former is fine; the latter violates "configurable, not customised" (§3.1) and should be avoided.
- **It is high-stakes.** Financial correctness and signatory validity are trust-critical. A document that routes to the wrong queue is an annoyance; a liquidation that mis-computes or mis-signs is a finding in an ISO 9001 / COA sense. First impressions of a new platform are set by its first module — a shaky financial module is an expensive place to make them.

---

## 5. Feasibility Verdict for "Start With Travel Reimbursement"

| Interpretation of "start with travel reimbursement" | Feasible? | Notes |
|---|---|---|
| Literally the first thing built, before foundation/auth | **No** | Violates the foundation floor (§3). Not a preference call — a dependency fact. |
| First **user-facing module** released after Phases 0–2 (deferring CSS-IS/DMWIS) | **Yes, but costly** | Forfeits the de-risking rationale (§7); requires a requirements session first; means building DMWIS-class workflow machinery outside DMWIS. |
| An **early standalone module** rolled out behind a flag, alongside/after the core, without displacing CSS-IS/DMWIS | **Yes — recommended path** | Fits the architecture (§2), mirrors how §22 treats "first new module after the core," keeps the plan's de-risking intact. |

The middle column is the crux: reimbursement *can* be first-to-users, but "first" still sits on top of an unavoidable core, and choosing it over the existing-asset path is a real trade, not a free reordering.

---

## 6. Recommended Model — Two Tracks

Make explicit in the plan the distinction §1 draws out:

- **Build Track** — the existing Phases 0–10, unchanged. This is *how the system is constructed and QA'd*.
- **Rollout Track** — a new, thin overlay describing *which working slices are exposed to which users, when*, each gated behind a feature flag. Example staging:
  - **R0 (internal only):** everything behind flags, no staff exposure. Ends at the current Phase 7 pilot gate.
  - **R1 (pilot cohort):** Records Officer + Director, DMWIS documents + migrated CSS-IS (this is exactly today's Q7 pilot — no change).
  - **R2…Rn (feature drip):** each subsequent module/feature (Admin rooms, announcements, Reports, and any **new** module such as reimbursement) flipped on for a widening cohort once its phase QA + a short live soak pass.

The Rollout Track costs almost nothing to add because the enabling machinery (flags, toggles, nav filtering) is already Day-1 (§2). It converts the plan's two-event release into a controllable sequence without touching the build order.

**Travel reimbursement then slots in as a scoped new module** on this track — the same way §22 names Meetings/Calendar as "the first new module after the core." Concretely:

1. Run a **requirements session** for reimbursement first (the gate the plan already imposes on WFP, Q6/§22): document types, the FMS checklist per travel class, signatory chain, liquidation deadlines, COA/ARTA touchpoints, and which existing DMWIS mechanisms it reuses.
2. Build it as a **vertical slice** on the core, reusing DMWIS's signature/routing/deadline services rather than forking them.
3. **Release behind a flag** to a small finance/traveller cohort, soak, then widen.

---

## 7. The Sequencing Trade-off the Author Must Own

The plan's phase order is not arbitrary — it *starts from what exists to de-risk*: CSS-IS is live and production-tested, DMWIS is spec'd to v5.4, and Phase 1 pulls shared auth straight out of CSS-IS's migrated data (§23, C-3). Leading with reimbursement inverts that: it starts from **nothing** (unscoped, unbuilt, high-stakes) and pushes the two proven assets behind it.

That can still be the right call **if** the author's goal is fastest visible value on the highest-pain everyday process (everyone travels; reimbursement friction is acute) rather than fastest de-risking. But it should be chosen with eyes open:

- **Keep DMWIS/CSS-IS first (plan as written):** lowest technical risk; reimbursement becomes an early add-on module once its home machinery exists. *Recommended default.*
- **Lead with reimbursement:** highest early user-visible value; accept a requirements session up front, DMWIS-class machinery built ahead of DMWIS, and the existing assets deferred.

This is a genuine product decision, not a technical blocker — the architecture supports either.

---

## 8. Concrete Enhancements to Fold Into the Plan

If the author accepts the direction, these are the minimal, non-disruptive additions:

1. **Add a Rollout Track section** (§6) alongside §23, defining flag-gated release stages R0…Rn distinct from build Phases 0–10.
2. **State the foundation floor explicitly** — "no user-facing feature precedes Phase 2 + the governance gate" — as a locked rollout rule, so no future re-sequencing accidentally violates the one-login promise.
3. **Register travel reimbursement as a named parked module** in §22 (today it lives only in the grounding companion), with a one-line dependency note: *"reuses DMWIS signature/routing/deadline core; requires a requirements session (as WFP)."*
4. **Add a per-module release checklist** to the phase-exit ritual: phase QA passed → flag on for cohort → short live soak → widen. One paragraph; reuses existing QA discipline.
5. **Extend the governance gate note (§24 #6)** to call out financial + personal data explicitly for any FMS-family module.

None of these change a locked decision; they make the plan's latent rollout capability explicit and give reimbursement a legitimate, scoped home.

---

## 9. Risks Specific to Feature-Phased Rollout

| Risk | Mitigation (mostly already in the plan) |
|---|---|
| A flag flipped on before a feature is truly done leaks half-built UX | Fail-safe-OFF flags (Q12) + the per-module release checklist (§8.4); never flip on phase-exit alone, add the live soak. |
| Reimbursement machinery duplicates DMWIS and diverges | Build reimbursement to consume DMWIS's signature/routing/deadline core, not fork it (§3.1 "configurable, not customised"). |
| Leading with reimbursement delays the CSS-IS data cutover, letting the live copy drift | The cutover is a single gated re-migration (C-2); keep that gate wherever CSS-IS lands in the order — do not let it slip indefinitely behind new modules. |
| Continuous release blurs "what changed for whom, when" | CHANGELOG discipline + login "What's new" (M-2) already exist; extend the changelog entry to record the cohort a flag was widened to. |
| Financial/personal data raises the governance bar | The Data Privacy Act gate (§24 #6) already blocks real data until cleared; treat reimbursement as squarely inside it. |

---

## 10. Open Questions for the Author

1. **Which "start"?** Is travel reimbursement meant to be the first *module released to users* (deferring CSS-IS/DMWIS, §7), or an *early add-on* on the existing critical path (recommended)?
2. **Scope trigger:** ready to commit a reimbursement requirements session (like WFP's, Q6) before it can be sequenced?
3. **Cohort:** who is the reimbursement pilot cohort — finance unit only, or all travellers from day one?
4. **Trade acceptance:** is fastest-visible-value worth deferring the plan's de-risking-from-existing-assets logic? (§7)

---

*Prepared as a feasibility/enhancement assessment. It proposes; it does not decide. The Build Execution Plan remains the single source of truth until the author folds any of the above into it.*
