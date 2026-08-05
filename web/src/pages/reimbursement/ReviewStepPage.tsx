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
import { Callout } from "../../components/Callout/Callout";
import {
  ErrorSummary,
  type ErrorSummaryItem,
} from "../../components/ErrorSummary/ErrorSummary";
import { SummaryList, type SummaryListRow } from "../../components/SummaryList/SummaryList";
import { TaskList } from "../../components/TaskList/TaskList";
import { WizardPage } from "../../layouts/WizardPage";
import { formatManilaDate, formatPeso } from "../../lib/format";
import {
  EMPTY_CHECKLIST_SUMMARY,
  checklistItemAnchor,
  checklistProgress,
  gateMessage,
} from "./checklist-status";
import { canPreparePacket } from "./claim-status";
import { ClaimStepGuard } from "./ClaimStepGuard";
import { useReturnReasons } from "./use-claim";
import { ClaimTotalsCard } from "./MoneyStepPage";
import { PacketPreview } from "./PacketPreview";
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

/**
 * Spec §11's promoted pre-check, at wizard step 5 (R-8).
 *
 * *"One click creates a warning-level auto-check shown at wizard step 5 —
 * 'Claims like yours are often returned because…'"*. This is that warning, and
 * four things about it are deliberate:
 *
 * 1. **It is advisory and can never gate.** It is not in `blocked`, does not
 *    touch the Submit button, and nothing it says is read by the packet gate.
 *    R-3's hard gate is about MISSING DOCUMENTS; conflating "often returned"
 *    with "incomplete" would let a statistic refuse a legitimate claim.
 * 2. **Fail-safe runs the OTHER way here.** Everywhere else the safe answer is
 *    to block or to flag; for an advisory it is to say nothing. So a failed or
 *    still-loading taxonomy fetch renders nothing at all — an unexplained
 *    warning is worse than no warning.
 * 3. **It carries the reasons, never the numbers.** How often a reason happens
 *    is other people's failures (spec §11, aggregates only, oversight-scoped);
 *    what usually goes wrong is guidance, and only the second belongs here.
 * 4. **It reads the same taxonomy the return dialog does**, so the wording a
 *    claimant is warned with is the wording an approver will pick — and one
 *    cached list means the two can never drift.
 */
function ReturnedOftenCallout() {
  const reasons = useReturnReasons();
  const promoted = (reasons.data ?? []).filter((reason) => reason.promoted);
  if (promoted.length === 0) return null;

  return (
    <Callout status="warn" title="Claims like yours are often returned because…">
      <ul className="flex list-disc flex-col gap-1 pl-5">
        {promoted.map((reason) => (
          <li key={reason.id}>{reason.label}</li>
        ))}
      </ul>
      <p className="mt-2 text-sm text-text-muted">
        This is a heads-up, not a blocker — you can still submit. Fixing any of
        these now saves a round trip.
      </p>
    </Callout>
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
      // A 422 from the packet gate needs the same pull: the panel below may be
      // empty precisely because we believed the packet was clear, and refetching
      // is what makes the path appear (spec §9.1 principle 4).
      if (
        error instanceof ApiError &&
        (error.status === 409 ||
          (error.status === 422 && error.code === "reimb_packet_incomplete"))
      ) {
        void queryClient.invalidateQueries({ queryKey: reimbKeys.claim(claim.id) });
      }
    },
  });

  const status = stepStatus(claim);
  const checklist = claim.checklist ?? EMPTY_CHECKLIST_SUMMARY;
  // `documents` is excluded here because its blockers are enumerated
  // item-by-item below — listing both the step and its five missing files
  // would double-count the same problem.
  const blockingSteps = WIZARD_STEPS.filter(
    (step) =>
      step.slug !== "review" &&
      step.slug !== "documents" &&
      status[step.slug] !== "done",
  );
  const blockingItems = checklist.blocking;
  const blocked = blockingSteps.length > 0 || blockingItems.length > 0;
  const isResubmit = claim.status === "returned";

  return (
    <WizardPage
      title="File a travel claim"
      steps={STEP_LABELS}
      current={stepNumber("review")}
      back={
        <Link
          to={stepPath(claim.id, "documents")}
          className="text-sm text-link underline"
        >
          Back to Documents
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
        <section className="flex flex-col gap-2">
          <h2 className="text-lg font-bold text-text">Documents</h2>
          {/* Check-your-answers is a SUMMARY; the full packet is one click
              away, and the blocking items are enumerated in the gate below. */}
          <SummaryList
            rows={[
              {
                key: "Required documents",
                value: checklistProgress(checklist),
                action: {
                  label: "Change",
                  to: `${stepPath(claim.id, "documents")}?from=review`,
                  visuallyHidden: "your documents",
                },
              },
            ]}
          />
        </section>

        {/* The packet as it stands, BEFORE the gate — so a claimant can read
            what they are about to file rather than discovering it after submit.
            Pre-submit it is always a draft copy: no reference number has been
            allocated yet, and the card says so. */}
        <PacketPreview claim={claim} canPrepare={canPreparePacket(claim)} />

        {/* R-8. ABOVE the gate on purpose: the gate says what you must fix, the
            advisory says what people usually get wrong, and reading them in
            that order would put "you cannot submit" after "here is a tip".
            Below the packet, because it is about the packet you just read. */}
        <ReturnedOftenCallout />

        {/* Spec §9.3 step 5: "Submit disabled until required items clear, with
            the blocking items listed inline." GOV.UK would keep the button
            enabled; we follow the spec, but mitigate the a11y cost — the button
            stays VISIBLE (the goal is legible), the reason sits immediately
            above it and is aria-describedby-linked, and every blocker links to
            its own fix. This panel must therefore never be collapsible: a
            disabled button is not focusable, so some screen readers skip its
            description. Recorded in the module delta register. */}
        {blocked ? (
          <section
            id="submit-gate"
            aria-labelledby="submit-gate-heading"
            className="rounded-md border border-status-blocked bg-surface p-4"
          >
            <h2 id="submit-gate-heading" className="text-base font-bold text-text">
              {blockingItems.length > 0
                ? gateMessage(checklist)
                : "Finish these before you submit"}
            </h2>
            <ul className="mt-2 flex list-disc flex-col gap-1 pl-5">
              {blockingSteps.map((step) => (
                <li key={step.slug}>
                  <Link
                    to={stepPath(claim.id, step.slug)}
                    className="text-base text-link underline"
                  >
                    {step.label}
                  </Link>
                </li>
              ))}
              {blockingItems.map((item) => (
                <li key={item.catalog_id}>
                  <Link
                    to={`${stepPath(claim.id, "documents")}#${checklistItemAnchor(
                      item.catalog_id,
                    )}`}
                    className="text-base text-link underline"
                  >
                    {item.label}
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        <div>
          <Button
            type="button"
            disabled={blocked}
            aria-describedby={blocked ? "submit-gate-heading" : undefined}
            loading={submit.isPending}
            onClick={() => submit.mutate()}
          >
            {isResubmit ? "Resubmit claim" : "Submit claim"}
          </Button>
          <p className="mt-2 text-sm text-text-muted">
            {isResubmit
              ? "Resubmitting recomputes your totals and restarts the approval chain."
              : "Submitting assigns your RB reference and sends the claim to your division chief."}
          </p>
        </div>
      </div>
    </WizardPage>
  );
}
