import { useId, type KeyboardEvent } from "react";
import { Link } from "react-router";
import type { LucideIcon } from "lucide-react";
import { Search } from "lucide-react";

export interface QueryBarResult {
  /** Stable key. On the landing this is the destination path. */
  id: string;
  label: string;
  to: string;
  icon?: LucideIcon;
  /** Optional muted second line — on the landing, the destination's description. */
  meta?: string;
}

export interface QueryBarProps {
  /** The visible field label. Required — there is no placeholder-only mode. */
  label: string;
  value: string;
  onValueChange: (next: string) => void;
  /** Heading above the list — the page's answer to "what is this list?" */
  resultsHeading: string;
  /** Already gated, already matched, already ordered. Rendered exactly as given. */
  results: QueryBarResult[];
  /** One sentence, announced politely. Empty while idle so nothing fires on load. */
  statusText: string;
  placeholder?: string;
  id?: string;
  /**
   * Names the `search` landmark. Omit unless a page has TWO search regions to
   * tell apart — the field's own label already names the control, and giving
   * the landmark the same string produces two things with one accessible name.
   */
  landmarkLabel?: string;
}

/**
 * ui-standards §3.24 — the Query bar. A labelled search field over destinations
 * PLUS the one results list beneath it; the two are a single accessibility unit
 * and are deliberately not split across caller and component, because the
 * describedby + live-region + list wiring is exactly the part a second consumer
 * would re-invent and get wrong.
 *
 * **It is a search field, NOT an ARIA combobox.** Radix ships no Combobox, so
 * that pattern would mean hand-rolling `role="combobox"` + `aria-expanded` +
 * `aria-activedescendant` + virtual focus — the hardest widget in ARIA, whose
 * 1.0→1.2 semantics changed incompatibly and whose announcements still differ
 * across NVDA/JAWS/VoiceOver and are unusable on iOS VoiceOver. §6 puts phones
 * first. What a combobox buys — an overlay popup and selection without moving
 * focus — this surface does not need: the content under the bar IS the list
 * being filtered. Real links in a real list are in the tab order by definition.
 *
 * **It filters nothing.** It renders the array it is handed, in the order it is
 * handed, and that array has already been gated by permission. It cannot reach
 * the nav registry, so it cannot offer a destination the user cannot open.
 *
 * Fully controlled with zero internal state, so the App shell can later drive
 * `value` from a router `?q=` with no change here.
 */
export function QueryBar({
  label,
  value,
  onValueChange,
  resultsHeading,
  results,
  statusText,
  placeholder,
  id,
  landmarkLabel,
}: QueryBarProps) {
  const autoId = useId();
  const inputId = id ?? `${autoId}-query`;
  const statusId = `${inputId}-status`;
  const headingId = `${inputId}-results`;

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    // The one keyboard nicety: users expect it from every search box, and
    // clearing without losing focus keeps them typing. Arrow keys do nothing
    // special — Tab is the platform's answer, and anything else is the
    // combobox we declined.
    if (event.key === "Escape" && value !== "") {
      event.preventDefault();
      onValueChange("");
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <form
        role="search"
        aria-label={landmarkLabel}
        // Enter is a deliberate no-op. "Enter goes to the first result" is an
        // invisible rule — nothing on screen says a result is selected — and if
        // the top match is wrong it moves the user somewhere they did not ask
        // for. The status sentence says "Choose one below" instead.
        onSubmit={(event) => event.preventDefault()}
      >
        <label htmlFor={inputId} className="block text-base font-medium text-text">
          {label}
        </label>
        <div className="relative mt-2">
          <Search
            aria-hidden="true"
            className="pointer-events-none absolute top-1/2 left-3 size-5 -translate-y-1/2 text-text-muted"
          />
          <input
            id={inputId}
            type="search"
            autoComplete="off"
            enterKeyHint="go"
            value={value}
            placeholder={placeholder}
            aria-describedby={statusId}
            onChange={(event) => onValueChange(event.target.value)}
            onKeyDown={handleKeyDown}
            className="min-h-11 w-full rounded-md border border-border bg-surface pr-3 pl-10 text-base text-text focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
          />
        </div>
      </form>

      {/* The answer, as a sentence. An unmatched query is NOT a validation
          error — no aria-invalid, no red border — so this is `status`, not
          `alert`, and it never steals focus. */}
      <p id={statusId} role="status" aria-live="polite" className="text-base text-text-muted">
        {statusText}
      </p>

      {results.length > 0 ? (
        <section aria-labelledby={headingId}>
          <h2 id={headingId} className="text-lg font-medium text-text">
            {resultsHeading}
          </h2>
          <ul className="mt-2 divide-y divide-border rounded-lg border border-border bg-surface">
            {results.map((result) => (
              <li key={result.id}>
                <Link
                  to={result.to}
                  className="flex min-h-11 flex-col justify-center gap-0.5 px-4 py-3 hover:bg-bg focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brand"
                >
                  <span className="flex items-center gap-2 text-base font-medium text-link underline">
                    {result.icon ? (
                      <result.icon aria-hidden="true" className="size-4 shrink-0" />
                    ) : null}
                    {result.label}
                  </span>
                  {result.meta ? (
                    <span className="text-sm text-text-muted">{result.meta}</span>
                  ) : null}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
