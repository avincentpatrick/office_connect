# UI Standards

Binding rules for every user-facing surface (standing rule 1: **all buttons,
text, forms, titles, tabs, icons, cards, etc. are uniform and templated —
every page uses the shared layout/component system**).

No frontend exists yet, so each section is tagged:

- **LOCKED** — binding now; violating it later is a defect.
- **DEFERRED** — placeholder with an explicit **fill-trigger** so this doc
  can't rot. *The trigger for implementation sections is "the first React
  surface", **not** "Phase 3"* — the build order puts the Reimbursement R-2
  wizard before the Phase 3 landing shell, so whichever lands first triggers
  the fill (sequencing decision is the user's; see `docs/modules/landing.md`).

---

## 1. Principles — LOCKED

Promoted platform-wide from the reimbursement spec §9.1:

1. **One thing per screen-moment** — never two competing primary actions.
2. **The checklist is the interface** — progress and next-step are always visible.
3. **Plain language first** — legal/technical wording is secondary text.
4. **Never block without a path** — every error states what to do next.
5. **Tokens only** — no raw hex colors, no raw px sizes in any component.

## 2. Design-token contract — LOCKED

The named CSS custom-property categories. The backend serves tenant values via
`GET /api/v1/config` → `branding`; components consume **only** these tokens:

| Category | Tokens (prefix `--oc-`) |
|---|---|
| Brand color | `color-brand`, `color-brand-contrast` |
| Surfaces | `color-bg`, `color-surface`, `color-border` |
| Text | `color-text`, `color-text-muted`, `color-link` |
| **Status (semantic)** | `status-done` (green) · `status-warn` (amber — due-soon/flagged) · `status-blocked` (red — overdue/blocked) · `status-waiting` (grey — waiting on external) |
| Spacing scale | `space-1 … space-8` (4-px base scale) |
| Type scale | `font-family`, `text-xs … text-3xl`, `weight-regular/medium/bold` |
| Shape | `radius-sm/md/lg`, `shadow-sm/md` |

Status colors are **semantic and platform-wide** — a green chip means the same
thing on every page of every module.

> **Neutral default values filled — Increment 3 (2026-07-23).** The concrete
> default values for every category above (a WCAG-AA palette, the 4-px spacing
> scale, the type scale, radius/shadow) now live in code as the single source of
> truth ([`office_connect/core/ui/tokens.py`](../../office_connect/core/ui/tokens.py),
> `NEUTRAL_TOKENS`) and are served by `GET /api/v1/config` under a **`tokens`**
> key (always present — a degraded/fail-safe config still returns the full
> neutral set, so the UI is never token-less). Tenant overrides go in
> `core_tenant_configs.branding.tokens` (same nested shape) and are deep-merged
> over the defaults; unknown token names are ignored (fail-safe). `to_css_variables()`
> flattens a token tree to `--oc-*` custom properties for the React/Tailwind
> layer (§7). The default color pairs are AA-verified in `tests/test_tokens.py`.

## 3. Component inventory — LOCKED (names & behavior contracts; visuals deferred)

No page may use a component outside this inventory; additions **amend this doc
first**. Required states in parentheses.

| Component | Contract |
|---|---|
| **Button** | primary / secondary / danger / disabled / loading. Exactly one primary per screen-moment. |
| **Form field** | label above, help text below, validation message states *what to do next* (never just "invalid"). Required marker uniform. |
| **Card** | title + optional status chip + body + optional action row. |
| **Tabs** | horizontal, keyboard-navigable; active state via tokens. |
| **Status chip / badge** | semantic status colors only (§2). |
| **Task list** (GOV.UK pattern) | the canonical checklist rendering: numbered sections, per-item status tag; drives every checklist screen. |
| **Stepper / wizard shell** | linear steps, progress indicator, back-safe. |
| **Timeline / tracker** | chronological events with actor + timestamp (Manila display). |
| **Pipeline-board card** | compact card for kanban-style boards. |
| **Dialog / confirm sheet** | destructive confirms state consequences in plain language. |
| **Empty state** | mandatory on every list — explains what will appear and the next action. |
| **Skeleton loader** | mandatory on every list/detail while loading. |
| **Toast / notification bell** | transient success/info; persistent items go to the bell. |

## 4. Layout templates — LOCKED

**No page is built outside one of these templates.** New template = amend
this doc first.

| Template | Use |
|---|---|
| **App shell** | Global chrome: top bar + nav (from `NAV_GROUPS`) + content slot. Every page renders inside it. |
| **List page** | Filter row → table/cards → pagination; empty state + skeleton mandatory. |
| **Wizard page** | Stepper shell + one step's form + task-list sidebar. |
| **Detail + right rail** | Main record + right rail (status, timeline, actions). |
| **Board page** | Pipeline columns of board cards. |
| **Admin / settings page** | Sectioned forms with per-section save. |

## 5. Copy standard — LOCKED

- Sentence case everywhere (buttons, titles, tabs, labels).
- No jargon in primary labels; legal wording as secondary text.
- Dates: `Jul 20, 2026` (Manila time). Money: `₱2,200.00`.
- Interface language: English.

## 6. Accessibility bar — LOCKED

- WCAG **AA** contrast, guaranteed via the token palette (checked once,
  inherited everywhere).
- All actions keyboard-reachable; visible focus states.
- Touch targets ≥ 44 px; approval surfaces are **phone-first**.
- Status conveyed by text + color, never color alone; lists are semantic and
  screen-reader announced.

## 7. Implementation choices — DEFERRED · *fill-trigger: first React surface*

To decide the session the React scaffold lands (and record here):
component-library structure, Tailwind config mapping the §2 tokens,
Storybook yes/no, exact breakpoints, and the icon set.
**Locked already:** exactly **one** icon library platform-wide — which one is
the deferred choice.

## 8. Per-component visual specs — DEFERRED · *fill-trigger: first build of each component*

Each §3 component gets its visual spec (spacing, states, exact markup)
appended here the session it is first implemented.

## 9. Theming / multi-tenant branding — PARTIALLY FILLED (Increment 3) · *remaining fill-trigger: tenant theming UI (Phase 3)*

**Filled (Increment 3):** the branding→token mapping and the neutral-defaults
fallback are now concrete — tenant `branding.tokens` (nested, same shape as
`NEUTRAL_TOKENS`) is deep-merged over the platform defaults by `build_tokens()`
and served via `GET /api/v1/config` (§2 note). Unknown keys are ignored; a
tenant that sets nothing gets the neutral Office-Connect defaults.

**Still deferred (Phase 3, first React surface):** the tenant-facing theming UI
(logo/name/brand-color editor + preview), the Tailwind config that renders the
served tokens into a `:root` block (§7), and per-tenant asset (logo) storage.
