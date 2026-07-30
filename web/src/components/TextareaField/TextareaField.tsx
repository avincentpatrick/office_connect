import type { ComponentPropsWithRef } from "react";
import { cx } from "../../lib/cx";
import { FieldChrome } from "../FormField/FieldChrome";

export interface TextareaFieldProps extends ComponentPropsWithRef<"textarea"> {
  id: string;
  label: string;
  help?: string;
  /** Validation message — must state what to do next, never just "invalid". */
  error?: string;
}

/**
 * ui-standards §3.2 (Form-field family, R-2-wizard) — native `<textarea>`
 * with the shared label/help/error chrome (multi-line prose: purpose,
 * comments).
 */
export function TextareaField({
  id,
  label,
  help,
  error,
  required,
  className,
  ...textarea
}: TextareaFieldProps) {
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
        <textarea
          id={id}
          required={required}
          rows={3}
          {...aria}
          className={cx(
            "min-h-20 rounded-md border bg-bg px-3 py-2 text-base text-text",
            error ? "border-status-blocked" : "border-border",
            "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand",
          )}
          {...textarea}
        />
      )}
    </FieldChrome>
  );
}
