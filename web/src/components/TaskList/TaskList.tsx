import type { ReactNode } from "react";
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
  /** Secondary line under the name — legal wording, or why the item applies. */
  detail?: ReactNode;
  /**
   * In-place control for a task completed HERE rather than on another page
   * (the reimbursement Documents step's uploads). Mutually exclusive with
   * `to` — an item either navigates or acts, never both.
   */
  action?: ReactNode;
  /** DOM id on the `<li>` — the cross-page deep-link target. */
  id?: string;
}

export interface TaskListSection {
  title: string;
  items: TaskListItem[];
}

/**
 * ui-standards §3.6 — the GOV.UK task-list pattern: numbered sections, one
 * status tag per item. This is the canonical checklist rendering ("the
 * checklist is the interface", §1) and drives every checklist screen.
 *
 * R-3 added the optional `action` / `detail` / `id` slots rather than forking a
 * second checklist component: the module's flagship checklist screen must not
 * be the one screen that does not use the checklist component.
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
              <li
                key={item.id ?? item.name}
                id={item.id}
                className="flex flex-col gap-2 py-3"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex flex-col">
                    {item.to ? (
                      <Link
                        to={item.to}
                        className="text-base text-link underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
                      >
                        {item.name}
                      </Link>
                    ) : (
                      // Muted reads as "you cannot do this yet" — right for an
                      // inert step, wrong for a row you act on right here.
                      <span
                        className={
                          item.action
                            ? "text-base text-text"
                            : "text-base text-text-muted"
                        }
                      >
                        {item.name}
                      </span>
                    )}
                    {item.hint ? (
                      <span className="text-sm text-text-muted">{item.hint}</span>
                    ) : null}
                  </div>
                  <StatusChip status={item.status}>{item.statusLabel}</StatusChip>
                </div>
                {item.detail ? (
                  <div className="text-sm text-text-muted">{item.detail}</div>
                ) : null}
                {item.action ? <div>{item.action}</div> : null}
              </li>
            ))}
          </ul>
        </li>
      ))}
    </ol>
  );
}
