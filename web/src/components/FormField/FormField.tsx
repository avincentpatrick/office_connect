import type { InputHTMLAttributes } from "react";
import { cx } from "../../lib/cx";

export interface FormFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  id: string;
  label: string;
  help?: string;
  /** Validation message — must state what to do next, never just "invalid". */
  error?: string;
}

/**
 * ui-standards §3.2 — label above, help below the label, actionable validation
 * message below the input. Seed ships a text input; Select/Textarea/date land
 * with the wizard. Pair page-level errors with ErrorSummary (same wording).
 */
export function FormField({ id, label, help, error, required, className, ...input }: FormFieldProps) {
  const helpId = help ? `${id}-help` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [helpId, errorId].filter(Boolean).join(" ") || undefined;

  return (
    <div className={cx("flex flex-col gap-1", className)}>
      <label htmlFor={id} className="text-sm font-medium text-text">
        {label}
        {required ? (
          <span aria-hidden="true" className="text-status-blocked">
            {" "}
            *
          </span>
        ) : null}
      </label>
      {help ? (
        <p id={helpId} className="text-sm text-text-muted">
          {help}
        </p>
      ) : null}
      <input
        id={id}
        required={required}
        aria-describedby={describedBy}
        aria-invalid={error ? true : undefined}
        className={cx(
          "min-h-11 rounded-md border bg-bg px-3 text-base text-text",
          error ? "border-status-blocked" : "border-border",
          "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand",
        )}
        {...input}
      />
      {error ? (
        <p id={errorId} className="text-sm font-medium text-status-blocked">
          {error}
        </p>
      ) : null}
    </div>
  );
}
