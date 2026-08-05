# Development Workflow Standard

Binding process rules for how Office-Connect is built across sessions.
This is the authoritative copy — `CLAUDE.md` carries only the condensed form.

---

## 1. Session lifecycle

This is a **multi-session build with an AI assistant**. The repository's
documentation is the only memory that survives between sessions, so the
lifecycle is non-negotiable:

1. **Start** — read the top of [`PROGRESS.md`](../../PROGRESS.md):
   the **Current Status** block and the **Next Session Prompt** say exactly
   where to resume. Confirm the prompt with the user before doing anything else.
2. **Work** — follow the standards in `docs/standards/`; record decisions as
   they happen (see §5).
3. **End** — run the session-end checklist (§2). A session is **not over**
   until every step has run.

## 2. Session-end checklist (MANDATORY)

Run in order, every session, no exceptions:

1. **Update `PROGRESS.md`** — add a new session-log entry (done / decisions /
   docs updated), refresh the **Current Status** block, update the phase
   tracker rows.
2. **Update touched module docs** — status tables, delta registers, and
   decision logs in `docs/modules/<module>.md` for every module worked on.
3. **Update standards docs if triggered** — new dependency → `tech-stack.md`;
   schema-convention decision → `database-standards.md`; UI decision →
   `ui-standards.md` (same session, not later).
4. **Update `CHANGELOG.md`** — add user-visible changes under `[Unreleased]`.
5. **Write the Next Session Prompt** — refresh **both** the one-line
   **▶ RESUME** and the detailed **▶ NEXT SESSION PROMPT** brief at the top of
   `PROGRESS.md` (§3 two-tier format). The outgoing session also archives the
   brief in its own session-log entry.
6. **Local git commit** — `git add -A` then
   `git commit -m "session(YYYY-MM-DD): <one-line summary>"`. **Local only.**
7. **Phase gate (only if a phase's QA gate passed this session)** — see §6.

## 3. Next Session Prompt standard

The handoff has **two tiers** at the top of `PROGRESS.md`, both refreshed every
session end:

1. **▶ RESUME** — a **one-line** pointer the user actually copies, naming the
   next unit of work (e.g. *"Resume Office-Connect — Stage A Increment 3"*). The
   assistant expands it by reading Current Status + the brief below + the cited
   module docs (the start-of-session ritual), then confirms before starting.
2. **▶ NEXT SESSION PROMPT** — the **detailed, self-contained brief** the
   assistant expands the one-liner into. Keep it complete so the resume works
   even without the one-liner:

```text
Context: <1–2 lines — where the project stands>
Task: <the exact next task, in imperative form>
Files: <files/dirs involved>
Acceptance: <how to know the task is done — command(s) + expected result>
Open questions for the user: <decisions needed, or "none">
```

Both tiers live near the top of `PROGRESS.md` (overwritten each session); the
detailed brief is archived in each session-log entry.

## 4. Git strategy

**Rule: commit per session, push per phase.**

- **Local commits** — at minimum one at every session end
  (`session(YYYY-MM-DD): <summary>`); additional logical commits during a
  session are encouraged (they are the rollback points).
- **Push + tag** — **only when a phase passes its QA gate** (§6). Tag
  `phase-<N>-complete` where the stage has an old phase number, else
  `stage-<letter>-complete` (Stage C has no old number — the tracker's *Old #*
  column is empty for it — so its gate tag is `stage-c-complete`).
  Reimbursement sub-phases, if ever tagged individually: `reimb-R<N>-complete`.
  Then push branch + tags. Never push mid-phase.
- **Remote** — `origin` = `github.com/avincentpatrick/office_connect`,
  **provisioned before the Phase 0 gate as required**. Tags on it:
  `phase-0-complete` (2026-07-23), `phase-2-complete` (2026-07-27),
  `stage-c-complete` (2026-08-05).
- **Branching** — `master` only for now; revisit when frontend phases begin.
- Commit messages: imperative mood; prefix `session(...)` for session-end
  commits, conventional prefixes (`feat:`, `fix:`, `chore:`, `docs:`) for
  logical mid-session commits.

## 5. Documentation update rules

Docs change **in the same session** as the thing they describe:

| When this happens… | …update this |
|---|---|
| Code touched in a module | `docs/modules/<module>.md` (status / plan / deltas) |
| Dependency added or bumped (`requirements.txt`, `package.json`, compose image) | `docs/standards/tech-stack.md` |
| Schema or naming decision made | `docs/standards/database-standards.md` |
| UI/component/token decision made | `docs/standards/ui-standards.md` |
| User-visible behavior changed | `CHANGELOG.md` `[Unreleased]` |
| Any decision of record | `PROGRESS.md` session entry **Decisions** list + the affected doc |

`references/` is **never edited** — it is read-only source material.

## 5a. Rule 10 — Shared service first (locked 2026-07-23)

> Before any module adds a table, service, or engine, check the
> **core-services registry** (`docs/master-plan.md` §1.1). If an equivalent
> capability exists in core, consume it via its interface. Duplication
> requires a **documented waiver** in the module doc's delta register.

Origin: owner directive 2026-07-22 ("everything connected, one workflow, not
duplicative"). Concrete consequences:

- **One workflow engine** (`core_workflow_*`) drives every approval/routing
  flow platform-wide — no module builds its own approval machinery.
- One instance each of: attachments/scanning, frozen-snapshot signatures,
  notifications, reference numbers, holiday/working-day calendar,
  checklist/requirements engine, template→PDF generation, search, report
  lineage, compliance-deadline calendar, external contacts, document-type/
  signatory taxonomy.
- Cross-module links go through spine keys (`core_activities`,
  `core_pap_codes`, staff/org units) — nullable/soft, no cross-module writes,
  no cross-module imports (`lint-imports` stays the enforcement).
- Every declared link in the master-plan connection matrix (§1.3) gets a
  cross-module integration test at SIT.

## 6. Phase QA-gate ritual

A phase (or reimbursement sub-phase) exits only when **all** of these hold:

1. The phase's automated QA gates are green (pytest + `lint-imports` +
   anything the phase's module doc names).
2. A plain-language manual test guide for the phase exists (module doc).
3. `CHANGELOG.md` `[Unreleased]` is promoted to a version number
   (versions align to phases; `APP_VERSION` constant bumped to match).
4. Tag `phase-<N>-complete` created; branch + tags **pushed** to the remote.
5. `PROGRESS.md` phase-tracker row updated — the **Pushed (tag / date)** cell
   is filled. That cell is the enforcement point for the push-per-phase rule.
