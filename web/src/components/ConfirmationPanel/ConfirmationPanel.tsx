import { useEffect, useRef, type ReactNode } from "react";

export interface ConfirmationPanelProps {
  title: string;
  referenceLabel: string;
  reference: string;
  children?: ReactNode;
}

/**
 * ui-standards §3.16 (R-2-wizard) — GOV.UK confirmation panel for a completed
 * transaction. The heading takes focus on mount (the post-submit announce —
 * same pattern as ErrorSummary); the reference renders large. Outline style
 * (`border-status-done` on `bg-surface`) keeps the AA guarantee token-driven.
 */
export function ConfirmationPanel({
  title,
  referenceLabel,
  reference,
  children,
}: ConfirmationPanelProps) {
  const headingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    headingRef.current?.focus();
  }, []);

  return (
    <section className="rounded-lg border-2 border-status-done bg-surface p-6 text-center">
      <h1
        ref={headingRef}
        tabIndex={-1}
        className="text-2xl font-bold text-text focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
      >
        {title}
      </h1>
      <p className="mt-2 text-base text-text">{referenceLabel}</p>
      <p className="text-3xl font-bold text-text">{reference}</p>
      {children ? <div className="mt-4 text-base text-text">{children}</div> : null}
    </section>
  );
}
