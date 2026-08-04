import { cx } from "../../lib/cx";
import { formatManilaDate } from "../../lib/format";

/**
 * ui-standards §3.22 — a deadline as remaining time against a total.
 *
 * Spec §9.2 names a "30-day countdown ring" for the liquidation tracker and
 * §6.2 puts the same countdown "on every liquidation surface from CA creation".
 *
 * Three rules this component exists to enforce (§3 amendment 2026-08-04):
 *
 * 1. **The ring is decoration; the text is the information.** The `<svg>` is
 *    `aria-hidden`, and every fact it depicts — days left, the due date, the
 *    state word — is real text beside it. A screen-reader user gets the content,
 *    not a description of a shape. §6's "never colour alone", applied to a
 *    graphic that encodes urgency twice (sweep AND hue), neither perceivable
 *    without sight.
 * 2. **It displays a server value and derives nothing.** `daysRemaining` and
 *    `state` arrive already computed on the record (api-standards §2). A browser
 *    with a wrong clock, or one outside Manila, must not be able to tell a
 *    traveller they still have time to liquidate.
 * 3. **"No deadline yet" is a state with words.** An advance whose trip has not
 *    happened has no clock. A full ring would read as plenty of time and an
 *    empty one as overdue; both would be lies, so it says "Not started".
 */

/** The server's verdict (`services/deadline.py`) — never recomputed here. */
export type DeadlineState = "on_track" | "due_soon" | "overdue";

const STATE_CLASSES: Record<DeadlineState, string> = {
  on_track: "text-status-done",
  due_soon: "text-status-warn",
  overdue: "text-status-blocked",
};

const STATE_LABELS: Record<DeadlineState, string> = {
  on_track: "On track",
  due_soon: "Due soon",
  overdue: "Overdue",
};

const SIZES = {
  // Both ≥44 px so a ring inside a link is still a legal touch target (§6).
  sm: { box: 44, stroke: 4, text: "text-xs" },
  md: { box: 72, stroke: 6, text: "text-lg" },
} as const;

/**
 * The COA liquidation window, used only to scale the arc — never to decide
 * urgency (that is `state`, from the server). A deadline that was set under a
 * longer configured window simply renders a full ring for longer, which is
 * honest: it still says "N days left" in words.
 */
const NOMINAL_WINDOW_DAYS = 30;

export function CountdownRing({
  daysRemaining,
  state,
  deadlineDate,
  size = "sm",
  className,
}: {
  /** Calendar days until the deadline; negative once past. `null` = no clock. */
  daysRemaining: number | null;
  /** Server-derived urgency. `null` = no clock. */
  state: DeadlineState | null;
  /** ISO date the countdown ends on. `null` = no clock. */
  deadlineDate: string | null;
  size?: keyof typeof SIZES;
  className?: string;
}) {
  const { box, stroke, text } = SIZES[size];
  const radius = (box - stroke) / 2;
  const circumference = 2 * Math.PI * radius;

  if (daysRemaining === null || state === null || deadlineDate === null) {
    return (
      <div className={cx("flex items-center gap-3", className)}>
        <svg
          width={box}
          height={box}
          aria-hidden="true"
          focusable="false"
          className="text-status-waiting"
        >
          <circle
            cx={box / 2}
            cy={box / 2}
            r={radius}
            fill="none"
            stroke="currentColor"
            strokeWidth={stroke}
            strokeDasharray="4 4"
            opacity={0.4}
          />
        </svg>
        <span className="text-sm text-text-muted">
          No liquidation deadline yet
        </span>
      </div>
    );
  }

  // Clamped so an overdue ring is empty rather than winding backwards, and a
  // long-window deadline is full rather than overflowing the circumference.
  const fraction = Math.max(0, Math.min(1, daysRemaining / NOMINAL_WINDOW_DAYS));
  const offset = circumference * (1 - fraction);
  const overdue = daysRemaining < 0;

  return (
    <div className={cx("flex items-center gap-3", className)}>
      <svg
        width={box}
        height={box}
        aria-hidden="true"
        focusable="false"
        className={STATE_CLASSES[state]}
      >
        <circle
          cx={box / 2}
          cy={box / 2}
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeWidth={stroke}
          opacity={0.2}
        />
        <circle
          cx={box / 2}
          cy={box / 2}
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          // Start the sweep at 12 o'clock rather than 3.
          transform={`rotate(-90 ${box / 2} ${box / 2})`}
        />
        <text
          x="50%"
          y="50%"
          dominantBaseline="central"
          textAnchor="middle"
          fill="currentColor"
          className={cx(text, "font-bold")}
        >
          {overdue ? `+${Math.abs(daysRemaining)}` : daysRemaining}
        </text>
      </svg>
      {/*
        The accessible content. Deliberately not `sr-only`: a sighted user
        reading "8" inside a ring cannot tell 8 days from 8 weeks, so the
        sentence earns its place visually too.
      */}
      <div className="text-sm">
        <p className={cx("font-medium", STATE_CLASSES[state])}>
          {STATE_LABELS[state]}
        </p>
        <p className="text-text-muted">
          {overdue
            ? `${Math.abs(daysRemaining)} day${Math.abs(daysRemaining) === 1 ? "" : "s"} overdue`
            : `${daysRemaining} day${daysRemaining === 1 ? "" : "s"} left`}
          {" · due "}
          {formatManilaDate(deadlineDate)}
        </p>
      </div>
    </div>
  );
}
