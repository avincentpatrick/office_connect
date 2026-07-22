# Module: Landing Shell & Query Bar

## 1. Status

**NOT STARTED. Phase slot: 3.**

## 2. Purpose

The platform's front door: React app shell (top bar, `NAV_GROUPS` navigation,
module cards) and the query bar that routes plain-language intents to modules
**and reports** ("generate CSMR", "FOI report") via `NAV_GROUPS`
`intent_keywords`.

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

- **Sequencing (user decision):** the Reimbursement R-2 wizard lands *before*
  Phase 3 in the current build order, so the shared shell/component library
  either gets pulled forward into R-2 or Phase 3 moves ahead of R-2.
  `ui-standards.md` keys its deferred sections to "first React surface"
  either way.
- Frontend implementation choices (Tailwind mapping, icon set, breakpoints) —
  deferred per `ui-standards.md` §7.

## 6. Plan

*(Filled at the module's requirements session.)*
