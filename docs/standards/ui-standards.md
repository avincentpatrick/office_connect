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
| **Button** | primary / secondary / danger / disabled / loading. Exactly one primary per screen-moment. A **gate-disabled** primary must be accompanied by an always-visible, `aria-describedby`-linked explanation of exactly what unblocks it, with a link to each blocker — never a bare disabled button (a disabled control is not focusable, so its description can be skipped). |
| **Form field** (family) | label above, help text below, validation message states *what to do next* (never just "invalid"). Required marker uniform. The family: text/date input (`FormField`), `SelectField`, `TextareaField`, `CheckboxField`, `RadioGroupField` (fieldset + legend) — one shared label/help/error/aria contract via the internal `FieldChrome` (plumbing, NOT page-usable). |
| **Card** | title + optional status chip + body + optional action row. |
| **Tabs** | horizontal, keyboard-navigable; active state via tokens. |
| **Status chip / badge** | semantic status colors only (§2). |
| **Task list** (GOV.UK pattern) | the canonical checklist rendering: numbered sections, per-item status tag; drives every checklist screen. Items may carry an optional `detail` line, an in-place `action` slot (for a task completed on the checklist itself rather than on another page), and a DOM `id` for cross-page deep links; `to` and `action` are **mutually exclusive** — an item either navigates or acts. |
| **Stepper / wizard shell** | linear steps, progress indicator, back-safe. |
| **Timeline / tracker** | chronological events with actor + timestamp (Manila display). |
| **Pipeline-board card** | compact card for kanban-style boards. Inert by default; given a destination (`to`) the **title** becomes a link with a stretched overlay, so the whole card is clickable while its accessible name stays the title alone. |
| **Dialog / confirm sheet** | destructive confirms state consequences in plain language; controlled mode (`open`/`onOpenChange`, optional trigger) for router-driven prompts. |
| **Empty state** | mandatory on every list — explains what will appear and the next action. |
| **Skeleton loader** | mandatory on every list/detail while loading. |
| **Toast / notification bell** | transient success/info; persistent items go to the bell. |
| **Error summary** (GOV.UK) | page-level `role=alert` that receives focus on mount and anchor-links to each failing field; wording **identical** to the inline validation messages. |
| **Summary list** (GOV.UK check-your-answers) | `<dl>` of key/value rows with an optional per-row "Change" link (accessible-name context suffix, e.g. "Change purpose"); empty values render "Not provided", never blank. |
| **Confirmation panel** | transaction-complete panel: title (focused on mount), reference label + the reference number rendered large; used once per completed transaction. |
| **Work-item row** | linked inbox/list row: reference + title, StatusChip right, one muted meta line; the My-Work rendering (NOT the Pipeline-board card — that is a board `<article>`, whose link, when it has one, is on the title under a stretched overlay rather than around the row). |
| **Chip group** | multi-select picker over a SHORT closed taxonomy: fieldset + legend, chip-styled labels over real checkboxes, selected / unselected / error states. |
| **Form dialog** | dialog whose body is a form — a decision that needs input before it can be made. Submit does NOT close the dialog; the caller closes it on success. |
| **File upload** | a real, label-associated `<input type="file">` with a keyboard-reachable drop zone as its `<label>`; drag-and-drop is a mouse-only enhancement over that one control (never a drop-only affordance). States: idle / dragging / busy / error / disabled. Announces completion in a polite live region; resets its value after every emit so the same file can be re-picked. `capture` is opt-in only — on mobile it FORCES the camera and removes the gallery option. |
| **Callout** | inline, status-coloured aside (§2 semantics) explaining a condition next to the decision it affects. `<section aria-labelledby>`; the status word is `sr-only` text so meaning never rides colour alone (§6). **Does not take focus and is not `role=alert`** — that is Error summary's job. |
| **Countdown ring** | a deadline rendered as remaining time against a total, in semantic colour (§2): green on track / amber due soon / red overdue. The ring itself is **decorative and `aria-hidden`** — the state is carried by adjacent real text ("12 days left · due Aug 2, 2026"), never by the arc or its colour. Takes a server-derived state and day count; it **computes nothing**, because a deadline a browser worked out is a deadline a wrong clock can get wrong. Renders an honest "not started" when there is no deadline yet, never a full or empty ring. |
| **Ranked bar list** | an ordered list of counts, largest first, each with a bar showing its share **of the largest row — never of a total**. Bars are `aria-hidden` decoration; every number is real text on the row (`valueText` is required for exactly that reason), so a screen reader hears "12 returns", not a rectangle. It **does not re-order** — the order arrives from the server and is the content. A zero row keeps its place and draws no bar at all. Optional per-row `meta` line and `action` slot. |
| **Query bar** | a labelled search field over destinations **plus the one results list beneath it** — the two are a single accessibility unit, never split across caller and component. A **search field, NOT an ARIA combobox**: `<form role="search">` + a real visible `<label>` + `<input type="search">` + a polite live region carrying one status sentence + results as real links in a real list. **It filters nothing** — it renders the array it is handed, in the order it is handed, and that array has already been gated. Fully controlled (no internal state), so it lifts into another surface unchanged. An unmatched query is **not a validation error**: no `aria-invalid`, no red border — the answer is a sentence. |

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

> **Inventory amendment 2026-08-03 (R-3):** rows 20–21 for the documentary
> packet. **File upload** — the wizard's Documents step needs per-item upload
> controls, and nothing in the inventory covered a file input. Deliberately no
> upload percentage: `fetch` exposes no upload progress and forking the one API
> wrapper onto `XMLHttpRequest` to draw a bar is not worth it; a spinner plus a
> live region is the honest state. **Callout** — spec §9.4 asks for amber
> callouts above the approve button. **Error summary was NOT stretched to cover
> this**: it is `role=alert`, focuses itself on mount, is red, and is headed
> "There is a problem" — all four are wrong for a non-blocking warning that is
> present on load, and it would re-steal focus from the decision bar on every
> render. Card was rejected too (no semantic colour). Rule of thumb: **Error
> summary for a problem you caused and must fix now; Callout for a condition you
> should know about while deciding.**
>
> **Task list was AMENDED rather than forked.** The §3 row says it "drives every
> checklist screen", and the reimbursement packet is the module's flagship
> checklist — building a second component for it would have made the one screen
> that most needs the pattern the one screen not using it. Passing `ReactNode`
> into a data-shaped props object follows `SummaryListRow.action`,
> `Card.actions` and `DetailPage.actions`.
>
> **Citation fix (same amendment):** two call sites cited a non-existent
> "ui-standards §14" for the client/server wording-parity rule. This document
> has nine sections; the rule is the **Error summary row of §3** — cite it as
> **§3.14**, as `ErrorSummary.tsx` already did. R-3 strengthens it: where a
> rule's wording can drift, TRANSPORT the server's sentence on the record
> (`gate_message` rides `ClaimDetail`) rather than duplicating it client-side. A
> client-side constant is a fallback only, and must name the backend symbol it
> mirrors in a comment.
>
> **Usage note 2026-08-04 (R-5) — NO new inventory row for the generated
> document card.** Spec §9.3 step 4 asks for generated documents to appear as
> "`Generated ✓` cards with preview". That ships as a page-local COMPOSITION of
> inventory pieces (`web/src/pages/reimbursement/GeneratedDocCard.tsx`: a
> bordered surface, a date, and a link) passed into the task list's existing
> `action` slot — not as a new component. §3 forbids a page using a component
> **outside** the inventory; it does not forbid composing inventory pieces on a
> page, which the same screen's file list already does. Promote it to §3 when a
> second module needs it — the discipline that kept the checklist engine's
> storage module-side at R-3.
>
> Two decisions inside that card are worth recording because they are easy to
> get wrong in the other direction:
> 1. **One chip, not two.** R-3 established two chips for an upload because the
>    ITEM being attached and the FILE being scanned are genuinely different
>    facts. A generated document has only one: it is born scan-clean, so its
>    file state and its item state are the same state. Repeating "Generated"
>    inside the card as well as on the task-list row would be noise wearing the
>    costume of honesty. The rule generalizes: **a second chip must earn itself
>    by reporting a second fact.**
> 2. **Preview is a link to a new tab, not an embedded frame.** Three inline PDF
>    viewers stacked in a task list are unusable on the phone this module is
>    designed for, and the browser's own viewer beats anything embedded. The new
>    tab is announced in an `sr-only` span (WCAG 3.2.5). The single embedded
>    packet preview an approver gets (spec §9.2) is a different surface. Note
>    the link only previews rather than downloads because the server sends
>    `Content-Disposition: inline` for system-generated PDFs — see
>    api-standards §9c; the client never asks for it.
>
> **Usage note 2026-08-04 (R-5-packet) — the embedded document preview.** Spec
> §9.2 promises the approver a "packet PDF preview".
> `pages/reimbursement/PacketPreview.tsx` ships it as another page-local
> composition (Card + StatusChip + Button + Callout + one `<iframe>`), on the
> same reasoning as the card above: one consumer is not yet a pattern. Three
> rules that DO generalize, and are binding on any future embedded preview:
> 1. **An `<iframe>` carries a `title`.** Without one it is announced as "frame"
>    and nothing else — a WCAG failure that costs one attribute to avoid.
> 2. **The frame is an enhancement over a link, never the only affordance.** iOS
>    Safari does not render a PDF in an iframe; it shows a blank box or a
>    download stub. So the new-tab link is present at every width and only the
>    FRAME is hidden below `lg`. This also keeps `DetailPage`'s single-node rule
>    intact — one node repositioned, never two nodes with duplicate ids.
> 3. **Absence is a state with copy, not an empty frame.** A record with no
>    document yet must say so in words (and, where the viewer may act, offer the
>    button that fixes it). Rendering a frame around nothing looks like a broken
>    page rather than an honest "not ready".
>
> A frame sits inside the page flow, so the §4 z-index ladder is unchanged: it
> never overlaps the sticky decision bar (`z-30`) or a dialog above it.

> **Inventory amendment 2026-08-04 (R-6-clock):** row 22, **Countdown ring**.
> Spec §9.2 names a "30-day countdown ring" on the liquidation tracker, and
> §6.2 puts the same countdown "on every liquidation surface from CA creation" —
> so unlike the two page-local compositions above, this one has three consumers
> on the day it ships (My-Work, the cash-advance list, the claim rail). Three
> consumers is what the "promote when a second appears" rule is waiting for.
>
> Three rules it establishes, binding on any future progress indicator:
> 1. **The ring is decoration; the text is the information.** The arc is
>    `aria-hidden` and every fact it depicts — days left, the date, the state
>    word — is present as real text beside it. A screen-reader user gets the
>    same content, not a description of a shape. This is §6's "never colour
>    alone" applied to a graphic: the ring encodes urgency twice over (sweep and
>    hue) and both are unavailable to a non-visual reader.
> 2. **A countdown displays a server value; it never derives one.** `days_left`
>    and the on-track/due-soon/overdue verdict arrive on the record already
>    computed (api-standards §2). A browser in the wrong timezone, or with a
>    wrong clock, must not be able to tell a traveller they still have time to
>    liquidate — the same doctrine that keeps money server-side.
> 3. **"No deadline yet" is a state with words.** An advance whose trip has not
>    happened has no clock. Rendering a full ring (looks like plenty of time) or
>    an empty one (looks overdue) would both be lies; the component says "not
>    started" instead.
>
> **No new Table row, again.** The cash-advance list reuses **Work-item row**,
> whose contract ("reference + title, StatusChip right, one muted meta line") is
> exactly an advance's shape — DV number, amount, status, deadline. The §3
> deferral recorded at R-2-wizard therefore still stands unclaimed.
>
> **Test-harness note:** `test/a11y.ts` runs axe with `iframes: false`. jsdom
> gives an `<iframe>` no real window, so axe throws while trying to message it.
> The frame ELEMENT's own rules still run; only its inner content is skipped,
> and that content is a PDF the browser renders, not markup we author.

> **Inventory amendment 2026-08-06 (R-8):** row 23, **Ranked bar list**. Spec
> §9.2's Insights row names a "ranked return-reasons bar list" and nothing in
> the inventory covered it. It is a component rather than another page-local
> composition (the R-5 / R-5-packet answer) for one reason: **a bar encodes a
> quantity, and an encoding is exactly what §3 exists to standardize.** The
> per-diem table deferred at R-2-wizard is markup — a `<table>` carries its own
> semantics and a screen reader reads every cell. A bar carries none, so getting
> it wrong is an accessibility defect rather than an inconsistency, and the next
> consumer (Stage H's KPI surface) would get it wrong independently.
>
> It is built to the **Countdown ring doctrine** above, and adds two rules of
> its own that bind any future quantity graphic:
> 1. **A bar is a share of the LARGEST ROW, never of a total.** Scaling to a sum
>    renders each bar as a percentage of the whole, which is a *rate* — a claim
>    the underlying data usually cannot support (here the denominator would be
>    submissions, which is spec §13 and Stage H). A component that makes a rate
>    easy to draw is a component that will draw one nobody computed.
> 2. **Zero draws nothing, and keeps its row.** A hairline bar is
>    indistinguishable from a real small value, and on this surface the zero row
>    is the most valuable one on the screen — it is what a successful promotion
>    looks like.
>
> The component **does not sort**. The order arrives from the server and IS the
> content, so a client-side re-sort would be a second ranking to keep in step
> with the first.

> **Inventory amendment 2026-08-06 (Stage D Increment 1):** row 24, **Query
> bar** — the platform's front door. It is a component rather than another
> page-local composition (the R-5 / R-5-packet answer) for R-8's reason: **what
> would be got wrong here is an accessibility contract, not a layout**, and the
> next consumer — the same bar lifted into the App shell — would get it wrong
> independently.
>
> **It is a search field, NOT an ARIA combobox, and that is this row's main
> content.** Four reasons, because the pull toward a combobox is strong and the
> failure is invisible to sighted testing:
> 1. **Radix ships no Combobox.** The pattern therefore means hand-rolling
>    `role="combobox"` + `aria-expanded` + `aria-controls` + `aria-autocomplete`
>    + `role="listbox"`/`option` **plus virtual focus** (DOM focus stays in the
>    input while `aria-activedescendant` moves) — the hardest widget in ARIA.
>    §7 permits Radix primitives inside `components/` *precisely so focus
>    management comes from the platform*; hand-rolling the one widget that most
>    needs a platform is the opposite of that policy.
> 2. **Its semantics changed incompatibly between ARIA 1.0/1.1 and 1.2**, and
>    `aria-activedescendant` is still announced differently by NVDA, JAWS and
>    VoiceOver — and is not usefully supported by iOS VoiceOver at all. §6 puts
>    phones first; a pattern that is weakest on the platform §6 prioritizes is
>    indefensible here.
> 3. **What a combobox buys, this surface does not need** — an overlay popup
>    (the content under the bar *is* the list being filtered, so there is
>    nothing underneath worth preserving) and selection without moving focus.
> 4. **Real links in a real list are in the tab order**, reachable by every
>    screen reader's links-list and lists-list navigation, and right-, middle-
>    and Cmd-clickable. §6 says "all actions keyboard-reachable": a link is that
>    *by definition*, a virtual `option` only if we implement it correctly.
>
> Three rules it establishes, binding on any future search or filter control:
> 1. **A real, visible `<label>`. A placeholder is not a label** — it disappears
>    on input, fails contrast, and is announced inconsistently.
> 2. **Results are real links in a real list**, in the tab order (rule 4 above).
> 3. **The control filters nothing.** It renders the array it is handed, in the
>    order it is handed, and that array has **already been gated by permission**.
>    A control able to reach the navigation registry itself could offer a
>    destination the user cannot open — api-standards §9f's mistake in a new
>    place. The matcher behind it (`web/src/app/nav-match.ts`) is generic over
>    `{label, intentKeywords}` and imports nothing from `app/nav.ts`, so the leak
>    is **structurally impossible rather than merely avoided**.
>
> Recorded so nobody "improves" it later: **no `aria-expanded`, no
> `aria-activedescendant`, no `aria-autocomplete`, no popup, no focus trap, no
> debounce, no recent-searches, no fuzzy scoring — and Enter is a deliberate
> no-op.** "Enter goes to the first result" is an *invisible* rule: nothing on
> screen says a result is selected, and if the top match is wrong it moves the
> user somewhere they did not ask for. Making it visible is the combobox we just
> declined. The status sentence says "Choose one below" and the first result is
> one Tab away. **Escape clears the query and keeps focus in the field** — the
> one keyboard nicety worth having, because users expect it from every search
> box. An unmatched query is not a validation error (no `aria-invalid`, no red
> border): it is a true answer, and §6's "status by text, never colour" applies
> to answers as much as to states.
>
> **No new dependency** (rule 9). `cmdk`, `downshift` and `fuse.js` were
> considered and rejected: a deterministic six-tier matcher over ≤7 destinations
> needs no library, and a fuzzy scorer would make *"nothing matches"* impossible
> to state honestly — which is the one sentence this surface exists to be able
> to say.

## 4. Layout templates — LOCKED

**No page is built outside one of these templates.** New template = amend
this doc first.

| Template | Use |
|---|---|
| **App shell** | Global chrome: top bar + nav (from `NAV_GROUPS`) + content slot. Every page renders inside it. |
| **List page** | Filter row → table/cards → pagination; empty state + skeleton mandatory. |
| **Wizard page** | Stepper shell + one step's form + task-list sidebar. |
| **Detail + right rail** | Main record + right rail (status, timeline) + an optional `actions` slot: sticky to the bottom of the viewport on a phone, in the flow below the record from `lg` up. |
| **Board page** | Pipeline columns of board cards, each column headed by its name plus a count and a money figure; skeleton + empty state mandatory, as on the List page. Scrolls horizontally on phones. |
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

> **Template note 2026-08-04 (R-7-queue) — the List page's `filters` slot,
> first real use.** Both earlier lists parked a Button there; the claim queue is
> the first page to put an actual filter in it. Three rules come out of it:
> 1. **The filter row is inventory components only** — a `SelectField` of named
>    *views*, not a bespoke control and not a row of ad-hoc toggles. A view is a
>    named question ("With FMS too long"), so the label carries the meaning and
>    the query string stays the server's business.
> 2. **The filter value belongs in the query key.** Two filters are two
>    different lists; one cache entry for both shows the user the last question
>    they asked instead of the one they are asking.
> 3. **An empty state must answer the question that was asked.** "Nothing here"
>    is wrong under a filter — the queue's follow-up view says *"No claim has
>    been with FMS longer than 10 working days"*, quoting the threshold the
>    server applied rather than a number the page invented.

> **Template amendment 2026-08-05 (R-7-board) — the Board page gains
> `loading` + a mandatory `emptyState`, and its headers carry numbers.**
> §3 makes a skeleton and an empty state mandatory on *every list*, and
> api-standards §9f's own words are that a board is a list with headers — so the
> board template was one short. Three rules:
> 1. **Skeleton per column, one whole-board empty state.** An un-skeletoned
>    board flashes three empty columns on every load, which reads as "there is
>    no work" rather than "not yet". The whole-board empty state fires only when
>    *every* column is empty; a single empty column keeps its header, because
>    "₱0.00 is with FMS" is an answer and a vanished column reads as a failure
>    to load.
> 2. **The count and the money go in a `<p>` BELOW the `<h2>`, never inside
>    it.** A screen-reader heading list has to read "With FMS", not
>    "With FMS 24 ₱1,284,300.00".
> 3. **A column header describes the whole column, not the cards under it**, and
>    says so when they differ ("Showing 20 of 137"), quoting the server's cap.
>    Nothing on the page re-derives a total from the cards it can see — that
>    under-reports by exactly what did not fit, while looking correct.

> **Doctrine restated (R-6-clock, reaffirmed R-7-queue and R-7-board): an admin
> surface is reachable by anyone and refused by the server.** The route is not
> role-gated; the nav item is, for *discoverability only*. A 403 renders as the
> server's own explanation in the page's empty state — never a blank page, never
> a paraphrase the FE then has to keep true.

> **Template note 2026-08-06 (Stage D Increment 1) — the landing is a plain
> content page, and §4 is UNCHANGED.** §8's template notes already record
> HomePage and the auth screens as rendering "as a plain content page inside the
> App shell"; the landing is that page grown up. No new template, for two
> reasons. **A template exists to enforce mandatory structure** — the List page's
> `loading`/`isEmpty`/`emptyState`, the Board page's per-column skeleton — and
> the landing **fetches nothing**, so it has no loading state and no
> server-driven empty state for a template to guarantee. There is nothing to
> enforce. And **one consumer is not a pattern**, which is the same promotion
> rule §3 applies to components (R-5, R-5-packet, R-6-clock). The App shell's
> `max-w-5xl` cap is adequate: the content is one column of at most six
> destinations, and the master plan's word for this surface is MINIMALIST — the
> anti-dashboard. **Fill-trigger for a real amendment:** the first landing that
> needs full-bleed or a second column.

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
- **Nav/permission gating — FILLED (Stage D Increment 1, 2026-08-06; the
  R-2-shell deferral is LIFTED).** `NAV_GROUPS` (`web/src/app/nav.ts`) filters on
  feature flags (absent = OFF) + **permission codes** from `/auth/me`, which now
  carries a sorted `permissions: string[]` resolved through the **same**
  version-keyed Redis cache `require_permission` reads — one resolver,
  `core/auth/dependencies.py::effective_permission_codes`, serving both the gate
  and the "me" surface, because two readers of the same set eventually disagree
  and the UI ends up offering a destination the server refuses (api-standards
  §9j).
  **`requiredRoles` is DELETED, not deprecated.** Three reasons, the third of
  which was not visible at R-2-shell:
  1. Authorization is on permission STRINGS everywhere else (api-standards §7).
     A role name in the client re-encodes a role→permission mapping that lives
     in the database and that an administrator can change with no code change.
  2. The four oversight items need "holds ANY of `reimb.claim.review` /
     `.fms_update` / `.approve`" — which is
     `modules/reimbursement/services/queue.py::OVERSIGHT_PERMS` **verbatim**,
     i.e. the server's own refusal rule rather than a paraphrase of it. Holding
     any one of the three is exactly equivalent to `oversight_scope()` returning
     a non-empty scope.
  3. **`me.roles` is a login-time snapshot.** `SessionStore.set_permissions_version`
     stamps the version onto live sessions but never rewrites the session's
     `roles` field, so a role granted *after* login did not change the nav until
     the user signed in again. A permission set read through the version-keyed
     cache lands on the **next request**, which is the promise api-standards §7
     already makes everywhere else. The old gate was not merely coarse — it was
     out of date.
  **The nav is still discoverability, not authorization.** §4's doctrine is
  unchanged: every route stays reachable by anyone and the server still refuses.
  What changed is that the client's guess now matches the server's rule instead
  of approximating it. **The nav also deliberately does NOT narrow by org
  SCOPE** — a scoped Admin Officer can genuinely open the queue, they just see
  less inside it, and shipping scope to the client would mean shipping the org
  tree to the client.

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
| Pipeline-board card | `<article class="relative">` compact: ref-no (muted xs) + StatusChip row, title, one meta line. With `to`: the title is a `<Link>` carrying `after:absolute after:inset-0`, and the article takes `focus-within:` ring styling — the visible focus indicator must follow the invisible overlay. |
| Dialog | Radix Dialog (portal, focus trap, Esc); overlay `bg-text/50`; centered `max-w-md` panel: title, plain-language consequence, Cancel (secondary) + confirm (danger when destructive). |
| Empty state | centered on `bg-surface` dashed-free panel: Lucide icon (`aria-hidden`), "what will appear" title, description, next-action slot. |
| Skeleton | `animate-pulse bg-surface` blocks (`row`/`block` variants), `aria-hidden`; `PageSkeleton` wraps in `role="status"` + sr-only label. |
| Toast / bell | Radix Toast provider/viewport (bottom-right, 5 s); success `CheckCircle2 status-done` / info `Info link`; `toast()` bus is callable outside React (`toast-bus.ts`). Bell = top-bar icon button, `aria-label` includes unread count; badge in-memory (feed API deferred). |
| Error summary | `role="alert"`, `tabIndex=-1` + focused on mount; "There is a problem" heading; list of anchor links (`#field-id`) with wording identical to inline errors; `border-2 border-status-blocked`. |
| Chip group | `<fieldset>` (bare group `id` for ErrorSummary anchors) + `<legend>`; wrapped `flex` of chips, each a `sr-only` checkbox + `<label>` `min-h-11 rounded-lg border-border`; selected = `peer-checked:border-brand bg-brand text-brand-contrast`; focus ring via `peer-focus-visible:`. |
| Form dialog | Dialog chrome (above) with a `<form>` body: title, optional muted description, caller's fields, then Cancel (secondary, wrapped in `Dialog.Close`) + submit (`type="submit"`, danger when destructive, `loading` while in flight). Submit is NOT wrapped in `Close`. Panel scrolls (`max-h-[90vh] overflow-y-auto`) — dialog forms grow on a phone. |
| Countdown ring | inline SVG: a track circle plus a `stroke-dasharray`/`dashoffset` arc in `currentColor`, the wrapper coloured `status-done` / `status-due` / `status-blocked` from the **server's** state. `<svg aria-hidden focusable="false">` with the number centered as SVG text for sighted readers, and the full sentence ("12 days left · due Aug 2, 2026 · On track") as real text beside the ring for everyone. `null` state renders a dashed track and "Not started" — never a full or empty arc. Sizes `sm` (list rows) / `md` (detail rails); both ≥44 px so a linked ring is a legal touch target. |
| Ranked bar list | `<ol aria-label>`; each `<li>` is label + `valueText` on one baseline row, then an `aria-hidden` track (`h-2 border-border bg-surface`) holding a `bg-brand` fill at `count / max` per cent, then an optional muted `meta` line with the row's `action` right-aligned. `max` is guarded to ≥1 so an empty or all-zero list divides safely and simply draws no fill. Neutral `brand`, never a semantic status colour: a ranking is not a verdict, and colouring the top row red would say "this is bad" about a number nobody has judged. |
| Query bar | `<form role="search">` (not the `<search>` element — jsdom/axe support is still patchy; a later swap) wrapping a real visible `<label>` above an `<input type="search" autoComplete="off" enterKeyHint="go">` `min-h-11 rounded-md border-border bg-surface`, `aria-describedby` the status line. Below the form, `<p role="status" aria-live="polite">` carries **one** sentence — the match count or the refusal — supplied by the page's copy module, empty while idle so nothing is announced on load. Then `<section aria-labelledby>` with an `<h2>` and a single `divide-y divide-border` `<ul>` of router-`Link` rows: `min-h-11` full-row padding (the whole row is the touch target), Lucide icon `aria-hidden`, label, then the destination's own muted description line. When there are no results the status sentence renders **alone** — no empty `<ul>`, no dangling heading. `onSubmit` prevents default and does nothing; `Escape` clears the value and keeps focus in the field. |

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
