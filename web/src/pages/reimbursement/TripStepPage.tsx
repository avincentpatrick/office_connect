import { useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useSearchParams } from "react-router";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { reimbKeys, updateClaim, type ClaimDetail } from "../../api/reimbursement";
import { Button } from "../../components/Button/Button";
import {
  ErrorSummary,
  type ErrorSummaryItem,
} from "../../components/ErrorSummary/ErrorSummary";
import { FormField } from "../../components/FormField/FormField";
import { RadioGroupField } from "../../components/RadioGroupField/RadioGroupField";
import { SelectField } from "../../components/SelectField/SelectField";
import { TextareaField } from "../../components/TextareaField/TextareaField";
import { TaskList } from "../../components/TaskList/TaskList";
import { WizardPage } from "../../layouts/WizardPage";
import { fieldIdFromPath, serverFieldErrors } from "../../lib/form-errors";
import {
  toTripFormValues,
  toTripPatch,
  TRIP_FIELD_ORDER,
  TRIP_KNOWN_FIELDS,
  tripSchema,
  YES_NO_OPTIONS,
  type TripFormValues,
} from "./claim-forms";
import { ClaimStepGuard } from "./ClaimStepGuard";
import { UnsavedChangesGuard } from "./UnsavedChangesGuard";
import { useRegions } from "./use-claim";
import { buildTaskSections, STEP_LABELS, stepNumber, stepPath } from "./wizard-steps";

export function TripStepPage() {
  return <ClaimStepGuard slug="trip">{(claim) => <TripForm claim={claim} />}</ClaimStepGuard>;
}

function TripForm({ claim }: { claim: ClaimDetail }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const fromReview = searchParams.get("from") === "review";
  const regions = useRegions();
  const leavingRef = useRef(false);
  const [serverErrors, setServerErrors] = useState<ErrorSummaryItem[]>([]);

  const form = useForm<TripFormValues>({
    resolver: zodResolver(tripSchema),
    defaultValues: toTripFormValues(claim),
  });

  const save = useMutation({
    mutationFn: (values: TripFormValues) => updateClaim(claim.id, toTripPatch(values)),
    onSuccess: (updated) => {
      queryClient.setQueryData(reimbKeys.claim(claim.id), updated);
      leavingRef.current = true;
      navigate(fromReview ? stepPath(claim.id, "review") : stepPath(claim.id, "itinerary"));
    },
    onError: (error) =>
      setServerErrors(
        serverFieldErrors(error, form.setError, TRIP_KNOWN_FIELDS).filter(
          (item) => !item.fieldId, // anchored ones re-enter via formState.errors
        ),
      ),
  });

  const errors = form.formState.errors;
  const clientItems: ErrorSummaryItem[] = TRIP_FIELD_ORDER.filter(
    (name) => errors[name]?.message,
  ).map((name) => ({
    message: errors[name]?.message as string,
    fieldId: fieldIdFromPath(name),
  }));
  const summaryItems = [...clientItems, ...serverErrors];

  const onSubmit = form.handleSubmit(
    (values) => {
      setServerErrors([]);
      save.mutate(values);
    },
    () => setServerErrors([]),
  );

  const regionOptions = (regions.data ?? []).map((region) => ({
    value: region.region_code,
    label: region.region_name
      ? `${region.region_name} (${region.region_code})`
      : region.region_code,
  }));

  return (
    <WizardPage
      title="File a travel claim"
      steps={STEP_LABELS}
      current={stepNumber("trip")}
      back={
        <Link to="/reimbursement" className="text-sm text-link underline">
          Back to My Work
        </Link>
      }
      taskList={<TaskList sections={buildTaskSections(claim)} />}
    >
      <UnsavedChangesGuard
        shouldBlock={() => form.formState.isDirty && !leavingRef.current}
      />
      <div className="flex flex-col gap-6">
        <section className="rounded-md border border-border bg-surface p-4">
          <h2 className="text-base font-medium text-text">Claimant</h2>
          <p className="text-base text-text">
            {claim.claimant.full_name ?? "—"}
            {claim.claimant.position_title ? ` · ${claim.claimant.position_title}` : ""}
          </p>
          <p className="text-sm text-text-muted">
            {[claim.claimant.division?.name, claim.claimant.section?.name]
              .filter(Boolean)
              .join(" · ") || "No division on record"}
          </p>
        </section>

        {summaryItems.length > 0 ? (
          <ErrorSummary
            key={`${form.formState.submitCount}-${save.failureCount}`}
            errors={summaryItems}
          />
        ) : null}

        <form onSubmit={onSubmit} noValidate className="flex max-w-xl flex-col gap-4">
          <FormField
            id="dpo_no"
            label="DPO number"
            help="From the Department Personnel Order authorizing the trip."
            required
            error={errors.dpo_no?.message}
            {...form.register("dpo_no")}
          />
          <FormField
            id="dpo_date"
            label="DPO date"
            type="date"
            required
            error={errors.dpo_date?.message}
            {...form.register("dpo_date")}
          />
          <TextareaField
            id="purpose"
            label="Purpose of travel"
            required
            error={errors.purpose?.message}
            {...form.register("purpose")}
          />
          <FormField
            id="destination"
            label="Destination"
            help="City or municipality of official travel."
            required
            error={errors.destination?.message}
            {...form.register("destination")}
          />
          <SelectField
            id="destination_region_code"
            label="Destination region"
            help="Sets the EO 77 per-diem rate cluster."
            options={regionOptions}
            placeholder="Select a region"
            required
            error={errors.destination_region_code?.message}
            {...form.register("destination_region_code")}
          />
          <FormField
            id="date_depart"
            label="Departure date"
            type="date"
            required
            error={errors.date_depart?.message}
            {...form.register("date_depart")}
          />
          <FormField
            id="date_return"
            label="Return date"
            type="date"
            required
            error={errors.date_return?.message}
            {...form.register("date_return")}
          />
          <RadioGroupField
            id="is_within_50km"
            legend="Is the destination within 50 km of your official station?"
            help="Within 50 km without an overnight stay, only transport fare is payable (EO 77)."
            options={YES_NO_OPTIONS}
            required
            error={errors.is_within_50km?.message}
            {...form.register("is_within_50km")}
          />
          <RadioGroupField
            id="overnight_stay"
            legend="Will the trip include an overnight stay?"
            options={YES_NO_OPTIONS}
            required
            error={errors.overnight_stay?.message}
            {...form.register("overnight_stay")}
          />
          <div>
            <Button type="submit" loading={save.isPending}>
              {fromReview ? "Save and return to review" : "Continue"}
            </Button>
          </div>
        </form>
      </div>
    </WizardPage>
  );
}
