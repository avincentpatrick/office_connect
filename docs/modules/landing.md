# Module: Landing Shell & Query Bar

## 1. Status

**NOT STARTED. Phase slot: 3.**

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
- Frontend implementation choices (Tailwind mapping, icon set, breakpoints) —
  deferred per `ui-standards.md` §7 (fill at R-2).
- Calendar surface scope detail (filters, per-role views) — Stage D
  requirements session.

## 6. Plan

*(Filled at the module's requirements session.)*
