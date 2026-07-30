/**
 * The wizard's single source of truth (R-2-wizard): step order, route paths,
 * and the task-list derivation. Save-and-return is server-side — every
 * Continue persists — so step completion derives from claim FIELD PRESENCE
 * (there is no completed-steps marker): the task list re-opens automatically
 * when the server clears stale `totals` after an edit.
 */

import type { ClaimDetail } from "../../api/reimbursement";
import type { TaskListSection } from "../../components/TaskList/TaskList";
import type { SemanticStatus } from "../../components/StatusChip/StatusChip";

export const WIZARD_STEPS = [
  { slug: "trip", label: "Trip" },
  { slug: "itinerary", label: "Itinerary" },
  { slug: "money", label: "Money" },
  { slug: "review", label: "Review and submit" },
] as const;

export type StepSlug = (typeof WIZARD_STEPS)[number]["slug"];

export const STEP_LABELS: string[] = WIZARD_STEPS.map((step) => step.label);

export function stepNumber(slug: StepSlug): number {
  return WIZARD_STEPS.findIndex((step) => step.slug === slug) + 1;
}

export function stepPath(claimId: number, slug: StepSlug | "confirmation"): string {
  return `/reimbursement/claims/${claimId}/${slug}`;
}

export type StepState = "done" | "in_progress" | "not_started" | "blocked";

const TRIP_REQUIRED = [
  "dpo_no",
  "dpo_date",
  "purpose",
  "destination",
  "destination_region_code",
  "date_depart",
  "date_return",
] as const satisfies readonly (keyof ClaimDetail)[];

export function stepStatus(claim: ClaimDetail): Record<StepSlug, StepState> {
  const filled = (field: (typeof TRIP_REQUIRED)[number]) => {
    const value = claim[field];
    return value !== null && value !== "";
  };
  const tripDone = TRIP_REQUIRED.every(filled);
  const tripStarted = TRIP_REQUIRED.some(filled);
  const itineraryDone = claim.legs.length > 0;
  const moneyDone = claim.fund_source !== null && claim.totals !== null;
  const moneyStarted = claim.fund_source !== null;
  const submitted = claim.status !== "draft" && claim.status !== "returned";

  return {
    trip: tripDone ? "done" : tripStarted ? "in_progress" : "not_started",
    itinerary: !tripDone ? "blocked" : itineraryDone ? "done" : "not_started",
    money: !itineraryDone
      ? "blocked"
      : moneyDone
        ? "done"
        : moneyStarted
          ? "in_progress"
          : "not_started",
    review: submitted
      ? "done"
      : tripDone && itineraryDone && moneyDone
        ? "not_started"
        : "blocked",
  };
}

export function firstIncompleteStep(claim: ClaimDetail): StepSlug {
  const status = stepStatus(claim);
  for (const step of WIZARD_STEPS) {
    if (status[step.slug] !== "done") return step.slug;
  }
  return "review";
}

const STEP_STATE_PRESENTATION: Record<
  StepState,
  { status: SemanticStatus; label: string; linked: boolean }
> = {
  done: { status: "done", label: "Completed", linked: true },
  in_progress: { status: "warn", label: "In progress", linked: true },
  not_started: { status: "warn", label: "Not started", linked: true },
  blocked: { status: "waiting", label: "Cannot start yet", linked: false },
};

/** The wizard sidebar — every linked item IS the save-and-return re-entry. */
export function buildTaskSections(claim: ClaimDetail): TaskListSection[] {
  const status = stepStatus(claim);
  return [
    {
      title: "Your claim",
      items: WIZARD_STEPS.map((step) => {
        const presentation = STEP_STATE_PRESENTATION[status[step.slug]];
        return {
          name: step.label,
          status: presentation.status,
          statusLabel: presentation.label,
          to: presentation.linked ? stepPath(claim.id, step.slug) : undefined,
        };
      }),
    },
  ];
}
