import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router";
import { ApiError } from "../../api/http";
import {
  reimbKeys,
  submitClaim,
  type ClaimDetail,
  type ClaimTotals,
} from "../../api/reimbursement";
import { Button } from "../../components/Button/Button";
import {
  ErrorSummary,
  type ErrorSummaryItem,
} from "../../components/ErrorSummary/ErrorSummary";
import { SummaryList, type SummaryListRow } from "../../components/SummaryList/SummaryList";
import { TaskList } from "../../components/TaskList/TaskList";
import { WizardPage } from "../../layouts/WizardPage";
import { formatManilaDate, formatPeso } from "../../lib/format";
import { ClaimStepGuard } from "./ClaimStepGuard";
import { ClaimTotalsCard } from "./MoneyStepPage";
import {
  buildTaskSections,
  STEP_LABELS,
  stepNumber,
  stepPath,
  stepStatus,
  WIZARD_STEPS,
} from "./wizard-steps";

export function ReviewStepPage() {
  return (
    <ClaimStepGuard slug="review">{(claim) => <ReviewForm claim={claim} />}</ClaimStepGuard>
  );
}

function change(claim: ClaimDetail, slug: "trip" | "itinerary" | "money", what: string) {
  return { label: "Change", to: `${stepPath(claim.id, slug)}?from=review`, visuallyHidden: what };
}

function tripRows(claim: ClaimDetail): SummaryListRow[] {
  return [
    { key: "Claimant", value: claim.claimant.full_name },
    { key: "DPO number", value: claim.dpo_no, action: change(claim, "trip", "DPO number") },
    {
      key: "DPO date",
      value: claim.dpo_date ? formatManilaDate(claim.dpo_date) : null,
      action: change(claim, "trip", "DPO date"),
    },
    { key: "Purpose", value: claim.purpose, action: change(claim, "trip", "purpose") },
    {
      key: "Destination",
      value: claim.destination,
      action: change(claim, "trip", "destination"),
    },
    {
      key: "Travel dates",
      value:
        claim.date_depart && claim.date_return
          ? `${formatManilaDate(claim.date_depart)} to ${formatManilaDate(claim.date_return)}`
          : null,
      action: change(claim, "trip", "travel dates"),
    },
    {
      key: "Within 50 km",
      value: claim.is_within_50km ? "Yes" : "No",
      action: change(claim, "trip", "the 50 km answer"),
    },
    {
      key: "Overnight stay",
      value: claim.overnight_stay ? "Yes" : "No",
      action: change(claim, "trip", "the overnight answer"),
    },
  ];
}

function itineraryRows(claim: ClaimDetail): SummaryListRow[] {
  return claim.legs.map((leg) => ({
    key: `Leg ${leg.seq}`,
    value: [
      leg.leg_date ? formatManilaDate(leg.leg_date) : null,
      leg.place,
      leg.transport_mode?.replace("_", " "),
      leg.fare ? formatPeso(leg.fare) : "no fare",
    ]
      .filter(Boolean)
      .join(" · "),
    action: change(claim, "itinerary", `leg ${leg.seq}`),
  }));
}

function moneyRows(claim: ClaimDetail): SummaryListRow[] {
  return [
    {
      key: "Other expenses",
      value: formatPeso(claim.other_total),
      action: change(claim, "money", "other expenses"),
    },
    {
      key: "Fund source",
      value: claim.fund_source === "GF_ORS" ? "General Fund (ORS)" : claim.fund_source === "TF_BUR" ? "Trust Fund (BUR)" : null,
      action: change(claim, "money", "the fund source"),
    },
  ];
}

function TotalsTable({ totals }: { totals: ClaimTotals }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-base text-text">
        <caption className="sr-only">Per-diem breakdown by day</caption>
        <thead>
          <tr className="border-b border-border text-sm text-text-muted">
            <th scope="col" className="py-2 pr-4 font-medium">Date</th>
            <th scope="col" className="py-2 pr-4 font-medium">Day</th>
            <th scope="col" className="py-2 pr-4 font-medium">Cluster</th>
            <th scope="col" className="py-2 pr-4 font-medium">%</th>
            <th scope="col" className="py-2 font-medium">Amount</th>
          </tr>
        </thead>
        <tbody>
          {totals.days.map((day) => (
            <tr key={day.date} className="border-b border-border">
              <td className="py-2 pr-4">{formatManilaDate(day.date)}</td>
              <td className="py-2 pr-4">{day.day_type.replace("_", " ")}</td>
              <td className="py-2 pr-4">{day.cluster ?? "—"}</td>
              <td className="py-2 pr-4">{day.pct}%</td>
              <td className="py-2">{formatPeso(day.amount)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ReviewForm({ claim }: { claim: ClaimDetail }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [serverErrors, setServerErrors] = useState<ErrorSummaryItem[]>([]);

  const submit = useMutation({
    mutationFn: () => submitClaim(claim.id),
    onSuccess: (updated) => {
      // Navigate BEFORE the cache write — updating first would re-render this
      // still-mounted step as the read-only detail for a frame (the guard
      // renders non-editable claims in place).
      navigate(stepPath(claim.id, "confirmation"), { replace: true });
      queryClient.setQueryData(reimbKeys.claim(claim.id), updated);
      void queryClient.invalidateQueries({ queryKey: reimbKeys.myWork() });
    },
    onError: (error) => {
      setServerErrors([
        {
          message:
            error instanceof ApiError
              ? error.message
              : "Something went wrong. Please try again.",
        },
      ]);
      // A 409 means the claim moved under us — refetch so the guard re-routes.
      if (error instanceof ApiError && error.status === 409) {
        void queryClient.invalidateQueries({ queryKey: reimbKeys.claim(claim.id) });
      }
    },
  });

  const status = stepStatus(claim);
  const blocking = WIZARD_STEPS.filter(
    (step) => step.slug !== "review" && status[step.slug] !== "done",
  );
  const isResubmit = claim.status === "returned";

  return (
    <WizardPage
      title="File a travel claim"
      steps={STEP_LABELS}
      current={stepNumber("review")}
      back={
        <Link to={stepPath(claim.id, "money")} className="text-sm text-link underline">
          Back to Money
        </Link>
      }
      taskList={<TaskList sections={buildTaskSections(claim)} />}
      asideExtra={claim.totals ? <ClaimTotalsCard totals={claim.totals} /> : undefined}
    >
      <div className="flex flex-col gap-6">
        {serverErrors.length > 0 ? (
          <ErrorSummary key={submit.failureCount} errors={serverErrors} />
        ) : null}

        <section className="flex flex-col gap-2">
          <h2 className="text-lg font-bold text-text">Trip</h2>
          <SummaryList rows={tripRows(claim)} />
        </section>
        <section className="flex flex-col gap-2">
          <h2 className="text-lg font-bold text-text">Itinerary</h2>
          <SummaryList rows={itineraryRows(claim)} />
        </section>
        <section className="flex flex-col gap-2">
          <h2 className="text-lg font-bold text-text">Money</h2>
          <SummaryList rows={moneyRows(claim)} />
          {claim.totals ? <TotalsTable totals={claim.totals} /> : null}
        </section>

        {blocking.length > 0 ? (
          <section className="rounded-md border border-status-warn bg-surface p-4">
            <h2 className="text-base font-bold text-text">
              Finish these before you submit
            </h2>
            <ul className="mt-2 flex list-disc flex-col gap-1 pl-5">
              {blocking.map((step) => (
                <li key={step.slug}>
                  <Link
                    to={stepPath(claim.id, step.slug)}
                    className="text-base text-link underline"
                  >
                    {step.label}
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        ) : (
          <div>
            <Button type="button" loading={submit.isPending} onClick={() => submit.mutate()}>
              {isResubmit ? "Resubmit claim" : "Submit claim"}
            </Button>
            <p className="mt-2 text-sm text-text-muted">
              {isResubmit
                ? "Resubmitting recomputes your totals and restarts the approval chain."
                : "Submitting assigns your RB reference and sends the claim to your division chief."}
            </p>
          </div>
        )}
      </div>
    </WizardPage>
  );
}
