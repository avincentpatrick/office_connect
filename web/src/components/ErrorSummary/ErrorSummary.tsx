import { useEffect, useRef } from "react";

export interface ErrorSummaryItem {
  message: string;
  /** id of the field to anchor to (matches FormField's id). */
  fieldId?: string;
}

/**
 * ui-standards §3.14 (added 2026-07-28) — GOV.UK error summary: page-level
 * role=alert that receives focus on mount and anchors to each failing field.
 * Wording must be IDENTICAL to the inline validation messages.
 */
export function ErrorSummary({
  errors,
  heading = "There is a problem",
}: {
  errors: ErrorSummaryItem[];
  heading?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    ref.current?.focus();
  }, []);

  if (errors.length === 0) return null;

  return (
    <div
      ref={ref}
      role="alert"
      tabIndex={-1}
      className="rounded-md border-2 border-status-blocked bg-bg p-4 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-status-blocked"
    >
      <h2 className="text-lg font-bold text-text">{heading}</h2>
      <ul className="mt-2 flex list-disc flex-col gap-1 pl-5">
        {errors.map((error, index) => (
          <li key={`${error.fieldId ?? index}-${error.message}`}>
            {error.fieldId ? (
              <a
                href={`#${error.fieldId}`}
                className="font-medium text-status-blocked underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
              >
                {error.message}
              </a>
            ) : (
              <span className="font-medium text-status-blocked">{error.message}</span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
