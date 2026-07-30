import type { ComponentPropsWithRef } from "react";
import { cx } from "../../lib/cx";

export interface RadioOption {
  value: string;
  label: string;
  hint?: string;
}

export interface RadioGroupFieldProps
  extends Omit<ComponentPropsWithRef<"input">, "type" | "id"> {
  /** Group id — each option input gets `${id}-${value}`. */
  id: string;
  legend: string;
  help?: string;
  /** Validation message — must state what to do next, never just "invalid". */
  error?: string;
  options: RadioOption[];
}

/**
 * ui-standards §3.2 (Form-field family, R-2-wizard) — `<fieldset>` +
 * `<legend>` radio group (fund source, yes/no attestations). react-hook-form
 * wiring: spread the SAME `register("name")` return onto the group — it lands
 * on every radio and the checked value drives the field.
 */
export function RadioGroupField({
  id,
  legend,
  help,
  error,
  required,
  className,
  options,
  ...input
}: RadioGroupFieldProps) {
  const helpId = help ? `${id}-help` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [helpId, errorId].filter(Boolean).join(" ") || undefined;

  return (
    // The fieldset carries the bare group id so ErrorSummary's #fragment
    // anchors resolve (the dots→dashes convention in lib/form-errors.ts).
    <fieldset
      id={id}
      className={cx("flex flex-col gap-1", className)}
      aria-describedby={describedBy}
    >
      <legend className="text-sm font-medium text-text">
        {legend}
        {required ? (
          <span aria-hidden="true" className="text-status-blocked">
            {" "}
            *
          </span>
        ) : null}
      </legend>
      {help ? (
        <p id={helpId} className="text-sm text-text-muted">
          {help}
        </p>
      ) : null}
      <div className="flex flex-col">
        {options.map((option) => (
          <div key={option.value} className="flex min-h-11 items-center gap-2">
            <input
              type="radio"
              id={`${id}-${option.value}`}
              value={option.value}
              required={required}
              className="size-5 accent-brand focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
              {...input}
            />
            <label htmlFor={`${id}-${option.value}`} className="text-base text-text">
              {option.label}
              {option.hint ? (
                <span className="block text-sm text-text-muted">{option.hint}</span>
              ) : null}
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
