import type { ComponentPropsWithRef } from "react";
import { cx } from "../../lib/cx";

export interface CheckboxFieldProps
  extends Omit<ComponentPropsWithRef<"input">, "type"> {
  id: string;
  label: string;
  hint?: string;
  /** Validation message — must state what to do next, never just "invalid". */
  error?: string;
}

/**
 * ui-standards §3.2 (Form-field family, R-2-wizard) — native checkbox left,
 * label right, 44-px row; hint/error id-linked via aria-describedby.
 */
export function CheckboxField({
  id,
  label,
  hint,
  error,
  className,
  ...input
}: CheckboxFieldProps) {
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;

  return (
    <div className={cx("flex flex-col gap-1", className)}>
      <div className="flex min-h-11 items-center gap-2">
        <input
          type="checkbox"
          id={id}
          aria-describedby={describedBy}
          aria-invalid={error ? true : undefined}
          className="size-5 accent-brand focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
          {...input}
        />
        <label htmlFor={id} className="text-base text-text">
          {label}
        </label>
      </div>
      {hint ? (
        <p id={hintId} className="text-sm text-text-muted">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={errorId} className="text-sm font-medium text-status-blocked">
          {error}
        </p>
      ) : null}
    </div>
  );
}
