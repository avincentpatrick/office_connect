import { useId, type ReactNode } from "react";
import { CircleAlert, CircleCheck, Clock, TriangleAlert } from "lucide-react";
import { cx } from "../../lib/cx";
import type { SemanticStatus } from "../StatusChip/StatusChip";

export interface CalloutProps {
  /** The same four platform semantics as StatusChip (§2) — no ad-hoc colours. */
  status: SemanticStatus;
  /** Short plain-language heading, sentence case. */
  title: string;
  /** Heading level, so the document outline stays honest. */
  as?: "h2" | "h3";
  /** Announce when the callout APPEARS in response to an action. Default off. */
  live?: "off" | "polite";
  children?: ReactNode;
  className?: string;
}

const BORDER: Record<SemanticStatus, string> = {
  done: "border-status-done",
  warn: "border-status-warn",
  blocked: "border-status-blocked",
  waiting: "border-status-waiting",
};

const TEXT: Record<SemanticStatus, string> = {
  done: "text-status-done",
  warn: "text-status-warn",
  blocked: "text-status-blocked",
  waiting: "text-status-waiting",
};

const ICON = {
  done: CircleCheck,
  warn: TriangleAlert,
  blocked: CircleAlert,
  waiting: Clock,
} as const;

/** §6: meaning never rides colour alone. The border is the colour; this is the text. */
const SR_WORD: Record<SemanticStatus, string> = {
  done: "Success",
  warn: "Warning",
  blocked: "Problem",
  waiting: "Waiting",
};

/**
 * ui-standards §3.20 (R-3) — an inline, status-coloured aside that explains a
 * condition next to the decision it affects (spec §9.4's amber flag callouts
 * above the approve button).
 *
 * Deliberately NOT `ErrorSummary`: that component is `role="alert"`, FOCUSES
 * ITSELF ON MOUNT, is red, and is headed "There is a problem". A flagged
 * auto-check is not a problem, must not steal focus from the decision bar, and
 * would re-steal it on every render of the claim page. Deliberately not `Card`
 * either: a Card has no semantic colour.
 */
export function Callout({
  status,
  title,
  as = "h3",
  live = "off",
  children,
  className,
}: CalloutProps) {
  const headingId = useId();
  const Icon = ICON[status];
  const Heading = as;

  return (
    <section
      aria-labelledby={headingId}
      {...(live === "polite" ? { role: "status" } : {})}
      className={cx(
        "rounded-md border-l-4 bg-surface p-4",
        BORDER[status],
        className,
      )}
    >
      <div className="flex items-center gap-2">
        <Icon aria-hidden="true" className={cx("size-5 shrink-0", TEXT[status])} />
        <Heading id={headingId} className="text-base font-bold text-text">
          <span className="sr-only">{SR_WORD[status]}: </span>
          {title}
        </Heading>
      </div>
      {children ? <div className="mt-1 text-base text-text">{children}</div> : null}
    </section>
  );
}
