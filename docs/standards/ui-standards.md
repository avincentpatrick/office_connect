# UI Standards

Binding rules for every user-facing surface (standing rule 1: **all buttons,
text, forms, titles, tabs, icons, cards, etc. are uniform and templated —
every page uses the shared layout/component system**).

Each section is tagged:

- **LOCKED** — binding now; violating it later is a defect.
- **DEFERRED** — placeholder with an explicit **fill-trigger** so this doc
  can't rot. *The trigger for implementation sections is "the first React
  surface", **not** "Phase 3"* — the build order puts the Reimbursement R-2
  wizard before the Phase 3 landing shell, so whichever lands first triggers
  the fill (sequencing decision is the user's; see `docs/modules/landing.md`).

> **The first React surface landed 2026-07-28 (Stage C R-2-shell, session 14)**
> — the `web/` Vite SPA: app shell, the 6 layout templates, the component
> inventory seed, and the token pipeline. §7 and §8 are filled below; §9's
> token-rendering half is filled.

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
| **Form field** (family) | label above, help text below, validation message states *what to do next* (never just "invalid"). Required marker uniform. The family: text/date input (`FormField`), `SelectField`, `TextareaField`, `CheckboxField`, `RadioGroupField` (fieldset + legend) — one shared label/help/error/aria contract via the internal `FieldChrome` (plumbing, NOT page-usable). |
| **Card** | title + optional status chip + body + optional action row. |
| **Tabs** | horizontal, keyboard-navigable; active state via tokens. |
| **Status chip / badge** | semantic status colors only (§2). |
| **Task list** (GOV.UK pattern) | the canonical checklist rendering: numbered sections, per-item status tag; drives every checklist screen. |
| **Stepper / wizard shell** | linear steps, progress indicator, back-safe. |
| **Timeline / tracker** | chronological events with actor + timestamp (Manila display). |
| **Pipeline-board card** | compact card for kanban-style boards. |
| **Dialog / confirm sheet** | destructive confirms state consequences in plain language; controlled mode (`open`/`onOpenChange`, optional trigger) for router-driven prompts. |
| **Empty state** | mandatory on every list — explains what will appear and the next action. |
| **Skeleton loader** | mandatory on every list/detail while loading. |
| **Toast / notification bell** | transient success/info; persistent items go to the bell. |
| **Error summary** (GOV.UK) | page-level `role=alert` that receives focus on mount and anchor-links to each failing field; wording **identical** to the inline validation messages. |
| **Summary list** (GOV.UK check-your-answers) | `<dl>` of key/value rows with an optional per-row "Change" link (accessible-name context suffix, e.g. "Change purpose"); empty values render "Not provided", never blank. |
| **Confirmation panel** | transaction-complete panel: title (focused on mount), reference label + the reference number rendered large; used once per completed transaction. |
| **Work-item row** | linked inbox/list row: reference + title, StatusChip right, one muted meta line; the My-Work rendering (NOT the Pipeline-board card — that is a board `<article>`, no link affordance). |
| **Chip group** | multi-select picker over a SHORT closed taxonomy: fieldset + legend, chip-styled labels over real checkboxes, selected / unselected / error states. |
| **Form dialog** | dialog whose body is a form — a decision that needs input before it can be made. Submit does NOT close the dialog; the caller closes it on success. |

> **Inventory amendment 2026-07-28 (R-2-shell):** **Error summary** added as
> the fourteenth component. master-plan §2 R-2 names it as a deliverable; it is
> page-level (coordinates many fields), not a Form-field state, so it needed
> its own inventory row — added via this amendment per the rule above.

> **Inventory amendment 2026-07-30 (R-2-wizard):** the **Form field** row
> becomes a family — §8 pre-authorized "Select/Textarea/date arrive with the
> wizard"; checkbox + radio-group (fieldset/legend) join for the wizard's
> attestations + fund-source questions. New rows 15–17: **Summary list**
> (check-your-answers), **Confirmation panel** (the RB- reference view), and
> **Work-item row** (the My-Work inbox rendering). **Dialog** gains a
> controlled mode for the unsaved-changes router prompt. All native-element
> based (no new Radix surface); zod + react-hook-form wire in per tech-stack §4
> (schemas validate SHAPE only — money/business rules stay server-side).
> **Recorded deferral:** the Review page's per-diem day breakdown renders as
> page-local semantic `<table>` markup (tokens-only, `overflow-x-auto`) — a
> reusable **Table** inventory item is deferred until a second consumer
> appears (amend §3 first when it does).

> **Inventory amendment 2026-08-03 (R-4-screens):** rows 18–19 for the approver
> surface. **Chip group** — spec §9.4 asks for "taxonomy chips" on the return
> dialog; on a phone a wrapped row of chips beats a tall column of checkbox rows
> for a 7-row taxonomy. Chips are a LOOK, not a widget: the component is a
> `<fieldset>` of real checkboxes with `sr-only` inputs driving `peer-checked:`
> styling, so keyboard traversal and the screen-reader group name come from the
> platform. Use it only for a short CLOSED taxonomy — a long or open-ended list
> is a Select. **Form dialog** — ConfirmDialog cannot host it: it has no body
> slot, and its confirm button is wrapped in `Dialog.Close`, so it closes
> unconditionally and in-dialog validation could never keep it open. FormDialog
> is a sibling with a real `<form>` whose submit is NOT wrapped in `Close`;
> **the caller closes it on success**, which is the only party that knows the
> request landed. Rule of thumb: **ConfirmDialog for a yes/no you cannot get
> wrong, FormDialog for a decision you can.** Both live in
> `components/Dialog/`. Validation wording inside a FormDialog must match the
> server's message for the same rule verbatim (§14).

## 4. Layout templates — LOCKED

**No page is built outside one of these templates.** New template = amend
this doc first.

| Template | Use |
|---|---|
| **App shell** | Global chrome: top bar + nav (from `NAV_GROUPS`) + content slot. Every page renders inside it. |
| **List page** | Filter row → table/cards → pagination; empty state + skeleton mandatory. |
| **Wizard page** | Stepper shell + one step's form + task-list sidebar. |
| **Detail + right rail** | Main record + right rail (status, timeline) + an optional `actions` slot: sticky to the bottom of the viewport on a phone, in the flow below the record from `lg` up. |
| **Board page** | Pipeline columns of board cards. |
| **Admin / settings page** | Sectioned forms with per-section save. |

> **Template amendment 2026-08-03 (R-4-screens):** **Detail + right rail**
> gains `actions` — spec §9.2 requires sticky Approve/Return on a phone, and
> this is the codebase's first sticky pattern. Two rules come with it, both
> learned the hard way:
> 1. **One node, repositioned — never two copies behind `lg:hidden` /
>    `hidden lg:block`.** CSS hides a node from sight, not from the DOM: a
>    duplicated action bar duplicates every `id` inside it and announces every
>    button twice to a screen reader. Reposition with
>    `sticky bottom-0 … lg:static`.
> 2. **Z-index ladder** (whole app, so a new sticky region has somewhere to
>    sit): sticky page regions `z-30` → dialog overlay `z-40` → dialog content
>    and toast viewport `z-50`. A sticky bar must stay *below* the overlay of a
>    dialog it opens. Sticky regions carry an opaque `bg-bg` and a `border-t`
>    so content stays legible scrolling underneath.

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

## 7. Implementation choices — FILLED (R-2-shell, 2026-07-28)

Decided the session the React scaffold landed (Stage C session 14). Exact
dependency pins live in [`tech-stack.md`](tech-stack.md) §4.

- **Component-library structure** — `web/src/components/<Name>/<Name>.tsx`
  with colocated `<Name>.test.tsx`; layout templates in `web/src/layouts/`;
  pages in `web/src/pages/` compose templates + inventory components only.
  Module page groups may nest one level (`web/src/pages/reimbursement/` —
  R-2-wizard convention extension); module display logic (status maps, wizard
  step derivation, zod schemas, hooks) lives in non-component sibling files in
  that directory. Contexts/hooks/non-component exports live in sibling
  non-component files (`auth-context.ts`, `config-context.ts`, `toast-bus.ts`)
  so HMR fast-refresh stays sound. Headless primitives (**Radix UI**, the
  unified `radix-ui` package) are allowed **only inside `web/src/components/`**
  — pages and layouts consume the inventory, never a primitive.
- **Tailwind config mapping the §2 tokens** — Tailwind v4 CSS-first config in
  `web/src/theme/tokens.css`: a baked `:root` block mirrors `NEUTRAL_TOKENS`
  (styles the pre-fetch paint; kept in sync same-session on any token change),
  then an **`@theme inline`** block maps every Tailwind namespace to
  `var(--oc-*)` so **runtime token injection re-themes every generated utility
  without a rebuild** (`injectTokens()` in `web/src/theme/tokens.ts` — the TS
  port of `to_css_variables()` — runs after the `/api/v1/config` fetch and sets
  the vars inline on `<html>`). The stock palette / type scale / weights /
  radii / shadows are wiped (`--color-*: initial` …) so **tokens-only (§1.5) is
  structural**: `bg-red-500` does not compile to anything. Utility ↔ token map:
  `bg-brand`, `text-brand-contrast`, `bg-bg`, `bg-surface`, `border-border`,
  `text-text`, `text-text-muted`, `text-link`,
  `*-status-{done,warn,blocked,waiting}`; `--spacing` = `--oc-space-1` (4-px
  base multiplier — discipline: steps 1–8 for §2 spacing, larger multiples for
  sizing only, e.g. `min-h-11` = the 44-px touch target); `text-xs…text-3xl`;
  `font-regular/medium/bold`; `rounded-sm/md/lg`; `shadow-sm/md`.
- **Storybook: NO** (recorded; revisit at Stage D if the consumer count grows)
  — the living catalog is the **DEV-only `/ui-foundation` route** (Admin
  template; registered only in development builds, statically eliminated from
  production bundles).
- **Breakpoints** — Tailwind 4 defaults: `sm` 40rem · `md` 48rem · `lg` 64rem
  · `xl` 80rem · `2xl` 96rem (rem-based → tracks user font-size settings).
  Phone-first by convention (§6): unprefixed utilities ARE the phone layout;
  the App-shell nav collapses below `md`; the wizard task-list sidebar stacks
  below `lg`.
- **Icon set: Lucide** (`lucide-react`) — the ONE platform icon library
  (kickoff decision 2026-07-28). Per-icon imports (tree-shaken); decorative
  icons always `aria-hidden`.
- **FE QA gate** — `npm run lint && npm run typecheck && npm run test &&
  npm run build`, run via the `web` container (tech-stack §5); paired with the
  backend pytest / lint-imports gates.
- **Nav/permission gating — recorded deferral** — `NAV_GROUPS`
  (`web/src/app/nav.ts`) filters on feature flags (absent = OFF) + role codes
  from `/auth/me`. `/auth/me` exposes roles, not permission strings; a
  self-permissions endpoint is deferred until a surface needs finer gating.

## 8. Per-component visual specs — SEEDED (R-2-shell, 2026-07-28) · *deepens as each component grows*

As-built seed specs. Common to all: tokens-only styling, ≥44-px touch targets
(`min-h-11`), visible `focus-visible` outline, status by text + color. Files
under `web/src/components/<Name>/`.

| Component | As-built seed (states · markup · a11y) |
|---|---|
| Button | primary `bg-brand/text-brand-contrast` · secondary `bg-surface + border-border` · danger `bg-status-blocked`; disabled 50 % opacity + not-allowed; loading = spinning Lucide `Loader2` + `aria-busy`, label kept, interaction blocked. Defaults `type="button"`. |
| Form field | label above (`htmlFor`), help below label (`aria-describedby`), error below input (`aria-invalid` + id-linked, border `status-blocked`); required = red asterisk (`aria-hidden`) + `required` attr. R-2-wizard: props widened to `ComponentPropsWithRef<"input">` so react-hook-form's `register()` spreads (React 19 ref-as-prop); `type="date"` is the documented date variant; the label/help/error chrome extracted into the internal `FieldChrome` shared by the family below. |
| SelectField | native `<select>` inside FieldChrome; `options: {value,label}[]` + optional disabled `""` placeholder option; same aria contract as Form field. |
| TextareaField | native `<textarea>` inside FieldChrome; `min-h` via spacing tokens. |
| CheckboxField | native checkbox left, label right, 44-px row; hint/error id-linked via `aria-describedby`. |
| RadioGroupField | `<fieldset>` + `<legend>` (label-weight), one native radio per option (option hints allowed), error inside the fieldset; RHF wiring = the same `register()` spread on every radio. Used for yes/no attestations and fund source. |
| Summary list | `<dl>`; each row `dt` muted key / `dd` value / optional `dd` "Change" router-Link (`text-link` underline) with an sr-only context suffix; empty value renders muted "Not provided". |
| Confirmation panel | `border-2 border-status-done` outline panel on `bg-surface`: `h1` title (`tabIndex=-1`, focused on mount — the post-submit announce), reference label, reference `text-3xl font-bold`. |
| Work-item row | `<li>` row in a divided list: router-Link (ref + title) left, StatusChip right, one muted meta line below (holder · days-in-state · next action, composed by the page). |
| Card | `<section>` `rounded-lg border-border bg-bg shadow-sm`; header = `h2` title + status-chip slot; body; footer action row. |
| Tabs | Radix Tabs (roving tabindex); active = `border-b-2 border-brand + text-text font-medium`. |
| Status chip | outline style: `border + text` in the semantic status color on `bg` (AA-verified pair); text label required. |
| Task list | numbered `<ol>` sections (`h3` "n. Title"), items in a divided `<ul>`: link (`text-link` underline) or inert muted name + hint, StatusChip right ("Cannot start yet" = `waiting` + no link). |
| Stepper | `<nav aria-label="Progress">`; visible "Step n of m: label"; per-step bars (done `status-done` / active `brand` / upcoming `border`) + `aria-current="step"`. |
| Timeline | `<ol>`; dot + connector rail; description then `actor · Manila datetime` muted line. |
| Pipeline-board card | `<article>` compact: ref-no (muted xs) + StatusChip row, title, one meta line. |
| Dialog | Radix Dialog (portal, focus trap, Esc); overlay `bg-text/50`; centered `max-w-md` panel: title, plain-language consequence, Cancel (secondary) + confirm (danger when destructive). |
| Empty state | centered on `bg-surface` dashed-free panel: Lucide icon (`aria-hidden`), "what will appear" title, description, next-action slot. |
| Skeleton | `animate-pulse bg-surface` blocks (`row`/`block` variants), `aria-hidden`; `PageSkeleton` wraps in `role="status"` + sr-only label. |
| Toast / bell | Radix Toast provider/viewport (bottom-right, 5 s); success `CheckCircle2 status-done` / info `Info link`; `toast()` bus is callable outside React (`toast-bus.ts`). Bell = top-bar icon button, `aria-label` includes unread count; badge in-memory (feed API deferred). |
| Error summary | `role="alert"`, `tabIndex=-1` + focused on mount; "There is a problem" heading; list of anchor links (`#field-id`) with wording identical to inline errors; `border-2 border-status-blocked`. |
| Chip group | `<fieldset>` (bare group `id` for ErrorSummary anchors) + `<legend>`; wrapped `flex` of chips, each a `sr-only` checkbox + `<label>` `min-h-11 rounded-lg border-border`; selected = `peer-checked:border-brand bg-brand text-brand-contrast`; focus ring via `peer-focus-visible:`. |
| Form dialog | Dialog chrome (above) with a `<form>` body: title, optional muted description, caller's fields, then Cancel (secondary, wrapped in `Dialog.Close`) + submit (`type="submit"`, danger when destructive, `loading` while in flight). Submit is NOT wrapped in `Close`. Panel scrolls (`max-h-[90vh] overflow-y-auto`) — dialog forms grow on a phone. |

**Template notes (§4 as-built):** all six templates exist in
`web/src/layouts/`. The **App shell** takes a `minimal` mode (brand bar only)
— the login / MFA-verify screens render inside it with a centered Card, so no
extra template exists for auth. List page enforces §3's mandatory
empty/skeleton states via required `loading`/`isEmpty`/`emptyState` props;
the pagination slot awaits the Stage-D envelope. **R-2-wizard amendments:**
the **Wizard page** gains an optional `asideExtra` slot rendered inside the
existing `<aside>` below the task list (the spec §9.3 running-totals rail —
Money/Review pass a compact "Claim totals" Card); the wizard's **post-submit
confirmation renders as a plain content page inside the App shell**
(ConfirmationPanel; precedent: HomePage/auth screens) — no stepper/task list
because the transaction is complete.

## 9. Theming / multi-tenant branding — PARTIALLY FILLED (Increment 3) · *remaining fill-trigger: tenant theming UI (Phase 3)*

**Filled (Increment 3):** the branding→token mapping and the neutral-defaults
fallback are now concrete — tenant `branding.tokens` (nested, same shape as
`NEUTRAL_TOKENS`) is deep-merged over the platform defaults by `build_tokens()`
and served via `GET /api/v1/config` (§2 note). Unknown keys are ignored; a
tenant that sets nothing gets the neutral Office-Connect defaults.

**Filled (R-2-shell, 2026-07-28):** the token *rendering* pipeline — baked
neutral `:root` fallback + `@theme inline` mapping + runtime `injectTokens()`
after the config fetch (§7). A tenant `branding.tokens` change re-brands the
whole UI on reload with **no rebuild**; a failed config fetch degrades to the
neutral tokens + all flags OFF (mirrors the backend fail-safe). The first
paint is blocked on the config fetch behind a neutral skeleton, so a branded
tenant never flashes the neutral theme.

**Still deferred (Phase 3):** the tenant-facing theming UI (logo/name/
brand-color editor + preview) and per-tenant asset (logo) storage.
