import { cx } from "../../lib/cx";

export interface StepperProps {
  steps: string[];
  /** 1-based index of the active step. */
  current: number;
}

/**
 * ui-standards §3.7 — linear steps with a progress indicator; back-safe (the
 * back affordance is the wizard template's slot, not the stepper's). Announces
 * "Step n of m" for screen readers.
 */
export function Stepper({ steps, current }: StepperProps) {
  return (
    <nav aria-label="Progress">
      <p className="mb-2 text-sm text-text-muted">
        Step {current} of {steps.length}: <span className="font-medium">{steps[current - 1]}</span>
      </p>
      <ol className="flex gap-2">
        {steps.map((step, index) => {
          const stepNumber = index + 1;
          const state =
            stepNumber < current ? "done" : stepNumber === current ? "active" : "upcoming";
          return (
            <li
              key={step}
              aria-current={state === "active" ? "step" : undefined}
              className="flex flex-1 flex-col gap-1"
            >
              <span
                aria-hidden="true"
                className={cx(
                  "h-1 rounded-sm",
                  state === "done" && "bg-status-done",
                  state === "active" && "bg-brand",
                  state === "upcoming" && "bg-border",
                )}
              />
              <span
                className={cx(
                  "text-xs",
                  state === "active" ? "font-medium text-text" : "text-text-muted",
                )}
              >
                {step}
              </span>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
