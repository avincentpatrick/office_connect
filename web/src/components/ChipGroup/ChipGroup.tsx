import { cx } from "../../lib/cx";

export interface ChipOption {
  value: string;
  label: string;
}

export interface ChipGroupProps {
  /** Group id — each option input gets `${id}-${value}`. */
  id: string;
  legend: string;
  help?: string;
  /** Validation message — must state what to do next, never just "invalid". */
  error?: string;
  options: ChipOption[];
  value: string[];
  onChange: (next: string[]) => void;
  className?: string;
}

/**
 * ui-standards §3.18 (R-4-screens) — multi-select chip group: a compact,
 * phone-first picker for a short closed taxonomy (spec §9.4's return reasons).
 *
 * Chips are a LOOK, not a widget: underneath this is a `<fieldset>` of real
 * checkboxes, so keyboard traversal, the screen-reader group name, and the
 * "n selected" announcement all come from the platform rather than from ARIA
 * we would have to maintain. The visible chip is the `<label>`; the input is
 * `sr-only` and drives the styling through `peer-checked:`.
 */
export function ChipGroup({
  id,
  legend,
  help,
  error,
  options,
  value,
  onChange,
  className,
}: ChipGroupProps) {
  const helpId = help ? `${id}-help` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [helpId, errorId].filter(Boolean).join(" ") || undefined;

  const toggle = (option: string) =>
    onChange(
      value.includes(option)
        ? value.filter((v) => v !== option)
        : [...value, option],
    );

  return (
    // The fieldset carries the bare group id so ErrorSummary's #fragment
    // anchors resolve (the dots→dashes convention in lib/form-errors.ts).
    <fieldset
      id={id}
      className={cx("flex flex-col gap-1", className)}
      aria-describedby={describedBy}
    >
      <legend className="text-sm font-medium text-text">{legend}</legend>
      {help ? (
        <p id={helpId} className="text-sm text-text-muted">
          {help}
        </p>
      ) : null}
      <div className="flex flex-wrap gap-2 pt-1">
        {options.map((option) => (
          <div key={option.value}>
            <input
              type="checkbox"
              id={`${id}-${option.value}`}
              className="peer sr-only"
              checked={value.includes(option.value)}
              onChange={() => toggle(option.value)}
              aria-invalid={error ? true : undefined}
            />
            <label
              htmlFor={`${id}-${option.value}`}
              className="flex min-h-11 cursor-pointer items-center rounded-lg border border-border bg-bg px-3 text-base text-text peer-checked:border-brand peer-checked:bg-brand peer-checked:text-brand-contrast peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-brand"
            >
              {option.label}
            </label>
          </div>
        ))}
      </div>
      {error ? (
        <p id={errorId} className="text-sm font-medium text-status-blocked">
          {error}
        </p>
      ) : null}
    </fieldset>
  );
}
