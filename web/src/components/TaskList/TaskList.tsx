import { Link } from "react-router";
import { StatusChip, type SemanticStatus } from "../StatusChip/StatusChip";

export interface TaskListItem {
  name: string;
  status: SemanticStatus;
  /** Plain-language status text, e.g. "Completed", "Not started", "Cannot start yet". */
  statusLabel: string;
  /** Route to the task; omit for inert items (e.g. cannot start yet). */
  to?: string;
  hint?: string;
}

export interface TaskListSection {
  title: string;
  items: TaskListItem[];
}

/**
 * ui-standards §3.6 — the GOV.UK task-list pattern: numbered sections, one
 * status tag per item. This is the canonical checklist rendering ("the
 * checklist is the interface", §1) and drives every checklist screen.
 */
export function TaskList({ sections }: { sections: TaskListSection[] }) {
  return (
    <ol className="flex flex-col gap-6">
      {sections.map((section, sectionIndex) => (
        <li key={section.title}>
          <h3 className="mb-2 text-lg font-bold text-text">
            {sectionIndex + 1}. {section.title}
          </h3>
          <ul className="divide-y divide-border border-t border-b border-border">
            {section.items.map((item) => (
              <li key={item.name} className="flex items-center justify-between gap-4 py-3">
                <div className="flex flex-col">
                  {item.to ? (
                    <Link
                      to={item.to}
                      className="text-base text-link underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
                    >
                      {item.name}
                    </Link>
                  ) : (
                    <span className="text-base text-text-muted">{item.name}</span>
                  )}
                  {item.hint ? <span className="text-sm text-text-muted">{item.hint}</span> : null}
                </div>
                <StatusChip status={item.status}>{item.statusLabel}</StatusChip>
              </li>
            ))}
          </ul>
        </li>
      ))}
    </ol>
  );
}
