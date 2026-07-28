import type { ReactNode } from "react";
import { cx } from "../../lib/cx";

export interface CardProps {
  title?: string;
  /** Optional StatusChip rendered beside the title. */
  status?: ReactNode;
  /** Optional action row rendered at the bottom. */
  actions?: ReactNode;
  className?: string;
  children: ReactNode;
}

/** ui-standards §3.3 — title + optional status chip + body + optional action row. */
export function Card({ title, status, actions, className, children }: CardProps) {
  return (
    <section className={cx("rounded-lg border border-border bg-bg shadow-sm", className)}>
      {title || status ? (
        <header className="flex items-center justify-between gap-2 border-b border-border px-4 py-3">
          {title ? <h2 className="text-lg font-medium text-text">{title}</h2> : <span />}
          {status}
        </header>
      ) : null}
      <div className="px-4 py-4 text-base text-text">{children}</div>
      {actions ? (
        <footer className="flex items-center justify-end gap-2 border-t border-border px-4 py-3">
          {actions}
        </footer>
      ) : null}
    </section>
  );
}
