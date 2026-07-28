import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { Inbox } from "lucide-react";

export interface EmptyStateProps {
  icon?: LucideIcon;
  /** What will appear here — plain language. */
  title: string;
  description?: string;
  /** The next action (usually a Button or link). */
  action?: ReactNode;
}

/** ui-standards §3.11 — mandatory on every list: what will appear + next action. */
export function EmptyState({ icon: Icon = Inbox, title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-lg border border-border bg-surface px-6 py-12 text-center">
      <Icon aria-hidden="true" className="size-8 text-text-muted" />
      <p className="text-lg font-medium text-text">{title}</p>
      {description ? <p className="max-w-md text-base text-text-muted">{description}</p> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}
