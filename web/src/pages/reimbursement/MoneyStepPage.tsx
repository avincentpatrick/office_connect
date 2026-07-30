import { useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  computeClaim,
  reimbKeys,
  updateClaim,
  type ClaimDetail,
  type ClaimTotals,
} from "../../api/reimbursement";
import { Button } from "../../components/Button/Button";
import { Card } from "../../components/Card/Card";
import {
  ErrorSummary,
  type ErrorSummaryItem,
} from "../../components/ErrorSummary/ErrorSummary";
import { FormField } from "../../components/FormField/FormField";
import { RadioGroupField } from "../../components/RadioGroupField/RadioGroupField";
import { SummaryList } from "../../components/SummaryList/SummaryList";
import { TaskList } from "../../components/TaskList/TaskList";
import { WizardPage } from "../../layouts/WizardPage";
import { formatPeso } from "../../lib/format";
import { fieldIdFromPath, serverFieldErrors } from "../../lib/form-errors";
import {
  FUND_SOURCE_OPTIONS,
  MONEY_FIELD_ORDER,
  MONEY_KNOWN_FIELDS,
  moneySchema,
  toMoneyFormValues,
  toMoneyPatch,
  type MoneyFormValues,
} from "./claim-forms";
import { ClaimStepGuard } from "./ClaimStepGuard";
import { UnsavedChangesGuard } from "./UnsavedChangesGuard";
import { buildTaskSections, STEP_LABELS, stepNumber, stepPath } from "./wizard-steps";

export function MoneyStepPage() {
  return (
    <ClaimStepGuard slug="money">{(claim) => <MoneyForm claim={claim} />}</ClaimStepGuard>
  );
}

/** Compact rail card — server strings through formatPeso, zero client math. */
export function ClaimTotalsCard({ totals }: { totals: ClaimTotals }) {
  return (
    <Card title="Claim totals">
      <dl className="flex flex-col gap-1 text-base text-text">
        <div className="flex justify-between gap-4">
          <dt className="text-text-muted">Per diem</dt>
          <dd>{formatPeso(totals.per_diem)}</dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt className="text-text-muted">Transport</dt>
          <dd>{formatPeso(totals.transport)}</dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt className="text-text-muted">Other</dt>
          <dd>{formatPeso(totals.other)}</dd>
        </div>
        <div className="flex justify-between gap-4 border-t border-border pt-1 font-bold">
          <dt>Grand total</dt>
          <dd>{formatPeso(totals.grand)}</dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt className="text-text-muted">To reimburse</dt>
          <dd>{formatPeso(totals.to_reimburse)}</dd>
        </div>
      </dl>
    </Card>
  );
}

function MoneyForm({ claim }: { claim: ClaimDetail }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const leavingRef = useRef(false);
  const [serverErrors, setServerErrors] = useState<ErrorSummaryItem[]>([]);

  const form = useForm<MoneyFormValues>({
    resolver: zodResolver(moneySchema),
    defaultValues: toMoneyFormValues(claim),
  });

  const saveAndCompute = useMutation({
    // One mutation, sequential awaits: persist the money fields, then ask the
    // server to compute. The PATCH result lands in the cache IMMEDIATELY so a
    // compute failure never leaves stale totals on screen — the server already
    // cleared them for changed inputs, and the task list re-opens Money.
    mutationFn: async (values: MoneyFormValues) => {
      const patched = await updateClaim(claim.id, toMoneyPatch(values));
      queryClient.setQueryData(reimbKeys.claim(claim.id), patched);
      return computeClaim(claim.id);
    },
    onSuccess: (updated) => {
      queryClient.setQueryData(reimbKeys.claim(claim.id), updated);
      leavingRef.current = true;
      navigate(stepPath(claim.id, "review"));
    },
    onError: (error) =>
      setServerErrors(
        serverFieldErrors(error, form.setError, MONEY_KNOWN_FIELDS).filter(
          (item) => !item.fieldId, // anchored ones re-enter via formState.errors
        ),
      ),
  });

  const errors = form.formState.errors;
  const clientItems: ErrorSummaryItem[] = MONEY_FIELD_ORDER.filter(
    (name) => errors[name]?.message,
  ).map((name) => ({
    message: errors[name]?.message as string,
    fieldId: fieldIdFromPath(name),
  }));
  const summaryItems = [...clientItems, ...serverErrors];

  const onSubmit = form.handleSubmit(
    (values) => {
      setServerErrors([]);
      saveAndCompute.mutate(values);
    },
    () => setServerErrors([]),
  );

  const fareRows = claim.legs.map((leg) => ({
    key: `Leg ${leg.seq} — ${leg.place ?? "itinerary leg"}`,
    value: leg.fare ? formatPeso(leg.fare) : "No fare",
  }));

  return (
    <WizardPage
      title="File a travel claim"
      steps={STEP_LABELS}
      current={stepNumber("money")}
      back={
        <Link
          to={stepPath(claim.id, "itinerary")}
          className="text-sm text-link underline"
        >
          Back to Itinerary
        </Link>
      }
      taskList={<TaskList sections={buildTaskSections(claim)} />}
      asideExtra={claim.totals ? <ClaimTotalsCard totals={claim.totals} /> : undefined}
    >
      <UnsavedChangesGuard
        shouldBlock={() => form.formState.isDirty && !leavingRef.current}
      />
      <div className="flex flex-col gap-6">
        {summaryItems.length > 0 ? (
          <ErrorSummary
            key={`${form.formState.submitCount}-${saveAndCompute.failureCount}`}
            errors={summaryItems}
          />
        ) : null}

        <section className="flex flex-col gap-2">
          <h2 className="text-lg font-bold text-text">Transport fares</h2>
          <p className="text-sm text-text-muted">
            From your itinerary — change them on the Itinerary step. The server
            computes every total.
          </p>
          <SummaryList rows={fareRows} />
        </section>

        <form onSubmit={onSubmit} noValidate className="flex max-w-xl flex-col gap-4">
          <FormField
            id="other_total"
            label="Other expenses"
            help="Total of other reimbursable expenses, e.g. 250.00. Leave blank for none."
            inputMode="decimal"
            error={errors.other_total?.message}
            {...form.register("other_total")}
          />
          <RadioGroupField
            id="fund_source"
            legend="Fund source"
            options={FUND_SOURCE_OPTIONS}
            required
            error={errors.fund_source?.message}
            {...form.register("fund_source")}
          />
          <div>
            <Button type="submit" loading={saveAndCompute.isPending}>
              Compute totals and continue
            </Button>
          </div>
        </form>
      </div>
    </WizardPage>
  );
}
