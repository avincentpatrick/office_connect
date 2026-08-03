import type { ReactNode } from "react";

export interface DetailPageProps {
  title: string;
  /** Status chip beside the title. */
  status?: ReactNode;
  /** Right rail: status card, timeline, actions — stacks below lg. */
  rail: ReactNode;
  /**
   * Decision buttons for this record — sticky to the bottom of the viewport on
   * a phone, in the flow below the record from `lg` up (ui-standards §4.4).
   */
  actions?: ReactNode;
  children: ReactNode;
}

/** ui-standards §4.4 — Detail + right rail: main record + status/timeline/actions rail. */
export function DetailPage({
  title,
  status,
  rail,
  actions,
  children,
}: DetailPageProps) {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-bold text-text">{title}</h1>
        {status}
      </div>
      <div className="grid gap-8 lg:grid-cols-[2fr_1fr]">
        <div className="flex flex-col gap-4">
          {children}
          {/*
            The decision follows the record it is about — ONE node, repositioned
            by breakpoint rather than rendered twice. (Two copies behind
            `lg:hidden`/`hidden lg:block` would duplicate every id inside them
            and announce every button twice to a screen reader; CSS hides a node
            from sight, not from the accessibility tree's ancestors.)

            Phone: sticky to the bottom edge so Approve/Return is reachable
            without scrolling back through the packet (spec §9.2 — approval
            surfaces are phone-first). Opaque background + top rule keep it
            legible over scrolling content; z-30 sits under the dialog overlay
            (z-40) these buttons open. From `lg` there is room to show the whole
            record, so it settles into the flow.
          */}
          {actions ? (
            <div className="sticky bottom-0 z-30 border-t border-border bg-bg py-3 lg:static lg:border-0 lg:py-0">
              {actions}
            </div>
          ) : null}
        </div>
        <aside aria-label="Record status" className="flex flex-col gap-4">
          {rail}
        </aside>
      </div>
    </div>
  );
}
