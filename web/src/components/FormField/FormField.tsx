import type { ComponentPropsWithRef } from "react";
import { cx } from "../../lib/cx";
import { FieldChrome } from "./FieldChrome";

export interface FormFieldProps extends ComponentPropsWithRef<"input"> {
  id: string;
  label: string;
  help?: string;
  /** Validation message — must state what to do next, never just "invalid". */
  error?: string;
}

/**
 * ui-standards §3.2 — the text/date input of the Form-field family (chrome in
 * FieldChrome; SelectField/TextareaField/CheckboxField/RadioGroupField are the
 * siblings). Props are `ComponentPropsWithRef` so react-hook-form's
 * `register()` spread — including its callback ref — typechecks (React 19
 * ref-as-prop). Pair page-level errors with ErrorSummary (same wording).
 */
export function FormField({
  id,
  label,
  help,
  error,
  required,
  className,
  ...input
}: FormFieldProps) {
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
        <input
          id={id}
          required={required}
          {...aria}
          className={cx(
            "min-h-11 rounded-md border bg-bg px-3 text-base text-text",
            error ? "border-status-blocked" : "border-border",
            "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand",
          )}
          {...input}
        />
      )}
    </FieldChrome>
  );
}
