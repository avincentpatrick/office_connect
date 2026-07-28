import type { ReactNode } from "react";
import { cx } from "../../lib/cx";

/** The four platform-wide semantic statuses (ui-standards §2) — never add ad-hoc colors. */
export type SemanticStatus = "done" | "warn" | "blocked" | "waiting";

const STATUS_CLASSES: Record<SemanticStatus, string> = {
  done: "border-status-done text-status-done",
  warn: "border-status-warn text-status-warn",
  blocked: "border-status-blocked text-status-blocked",
  waiting: "border-status-waiting text-status-waiting",
};

/**
 * ui-standards §3.5 — semantic status colors only; the text label is required
 * (status is conveyed by text + color, never color alone, §6).
 */
export function StatusChip({
  status,
  children,
  className,
}: {
  status: SemanticStatus;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cx(
        "inline-flex items-center rounded-sm border bg-bg px-2 py-0.5 text-sm font-medium",
        STATUS_CLASSES[status],
        className,
      )}
    >
      {children}
    </span>
  );
}
