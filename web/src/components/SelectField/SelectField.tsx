import type { ComponentPropsWithRef } from "react";
import { cx } from "../../lib/cx";
import { FieldChrome } from "../FormField/FieldChrome";

export interface SelectOption {
  value: string;
  label: string;
}

export interface SelectFieldProps extends ComponentPropsWithRef<"select"> {
  id: string;
  label: string;
  help?: string;
  /** Validation message — must state what to do next, never just "invalid". */
  error?: string;
  options: SelectOption[];
  /** Rendered as an empty-value first option (e.g. "Select a region"). */
  placeholder?: string;
}

/**
 * ui-standards §3.2 (Form-field family, R-2-wizard) — native `<select>` with
 * the shared label/help/error chrome. Options are data, not children, so pages
 * stay markup-free; requiredness is the schema's job (the placeholder keeps an
 * empty value zod can reject).
 */
export function SelectField({
  id,
  label,
  help,
  error,
  required,
  className,
  options,
  placeholder,
  ...select
}: SelectFieldProps) {
  return (
    <FieldChrome
      id={id}
      label={label}
      help={help}
      error={error}
      required={required}
      className={className}
    >
      {(aria) => (
        <select
          id={id}
          required={required}
          {...aria}
          className={cx(
            "min-h-11 rounded-md border bg-bg px-3 text-base text-text",
            error ? "border-status-blocked" : "border-border",
            "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand",
          )}
          {...select}
        >
          {placeholder !== undefined ? <option value="">{placeholder}</option> : null}
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      )}
    </FieldChrome>
  );
}
