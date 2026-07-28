import type { ReactNode } from "react";

export interface DetailPageProps {
  title: string;
  /** Status chip beside the title. */
  status?: ReactNode;
  /** Right rail: status card, timeline, actions — stacks below lg. */
  rail: ReactNode;
  children: ReactNode;
}

/** ui-standards §4.4 — Detail + right rail: main record + status/timeline/actions rail. */
export function DetailPage({ title, status, rail, children }: DetailPageProps) {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-bold text-text">{title}</h1>
        {status}
      </div>
      <div className="grid gap-8 lg:grid-cols-[2fr_1fr]">
        <div className="flex flex-col gap-4">{children}</div>
        <aside aria-label="Record status" className="flex flex-col gap-4">
          {rail}
        </aside>
      </div>
    </div>
  );
}
