import type { ReactNode } from "react";
import { cx } from "../../lib/cx";

interface FieldAria {
  "aria-describedby"?: string;
  "aria-invalid"?: true;
}

export interface FieldChromeProps {
  id: string;
  label: string;
  help?: string;
  /** Validation message — must state what to do next, never just "invalid". */
  error?: string;
  required?: boolean;
  className?: string;
  /** Render-prop: receives the computed aria props for the control. */
  children: (aria: FieldAria) => ReactNode;
}

/**
 * INTERNAL plumbing for the Form-field family (ui-standards §3.2) — label
 * above, help below the label, actionable validation message below the
 * control, shared by FormField/SelectField/TextareaField. NOT an inventory
 * item: pages must never import this — use a field component.
 */
export function FieldChrome({
  id,
  label,
  help,
  error,
  required,
  className,
  children,
}: FieldChromeProps) {
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
      {children({
        "aria-describedby": describedBy,
        "aria-invalid": error ? true : undefined,
      })}
      {error ? (
        <p id={errorId} className="text-sm font-medium text-status-blocked">
          {error}
        </p>
      ) : null}
    </div>
  );
}
