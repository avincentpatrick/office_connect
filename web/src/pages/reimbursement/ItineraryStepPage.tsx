import { useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useSearchParams } from "react-router";
import { useFieldArray, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { reimbKeys, replaceLegs, type ClaimDetail } from "../../api/reimbursement";
import { Button } from "../../components/Button/Button";
import { CheckboxField } from "../../components/CheckboxField/CheckboxField";
import {
  ErrorSummary,
  type ErrorSummaryItem,
} from "../../components/ErrorSummary/ErrorSummary";
import { FormField } from "../../components/FormField/FormField";
import { SelectField } from "../../components/SelectField/SelectField";
import { TaskList } from "../../components/TaskList/TaskList";
import { WizardPage } from "../../layouts/WizardPage";
import { fieldIdFromPath, serverFieldErrors } from "../../lib/form-errors";
import {
  emptyLeg,
  ITINERARY_KNOWN_FIELDS,
  itinerarySchema,
  LEG_FIELD_ORDER,
  toItineraryFormValues,
  toLegInputs,
  TRANSPORT_MODE_OPTIONS,
  type ItineraryFormValues,
} from "./claim-forms";
import { ClaimStepGuard } from "./ClaimStepGuard";
import { UnsavedChangesGuard } from "./UnsavedChangesGuard";
import { useRegions } from "./use-claim";
import { buildTaskSections, STEP_LABELS, stepNumber, stepPath } from "./wizard-steps";

export function ItineraryStepPage() {
  return (
    <ClaimStepGuard slug="itinerary">
      {(claim) => <ItineraryForm claim={claim} />}
    </ClaimStepGuard>
  );
}

function ItineraryForm({ claim }: { claim: ClaimDetail }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const fromReview = searchParams.get("from") === "review";
  const regions = useRegions();
  const leavingRef = useRef(false);
  const [serverErrors, setServerErrors] = useState<ErrorSummaryItem[]>([]);

  const form = useForm<ItineraryFormValues>({
    resolver: zodResolver(itinerarySchema),
    defaultValues: toItineraryFormValues(claim),
  });
  const { fields, append, remove } = useFieldArray({
    control: form.control,
    name: "legs",
  });

  const save = useMutation({
    mutationFn: (values: ItineraryFormValues) =>
      replaceLegs(claim.id, toLegInputs(values)),
    onSuccess: (updated) => {
      queryClient.setQueryData(reimbKeys.claim(claim.id), updated);
      leavingRef.current = true;
      navigate(fromReview ? stepPath(claim.id, "review") : stepPath(claim.id, "money"));
    },
    onError: (error) =>
      setServerErrors(
        serverFieldErrors(error, form.setError, ITINERARY_KNOWN_FIELDS).filter(
          (item) => !item.fieldId, // anchored ones re-enter via formState.errors
        ),
      ),
  });

  const errors = form.formState.errors;
  const clientItems: ErrorSummaryItem[] = [];
  const legsRootMessage = errors.legs?.root?.message ?? errors.legs?.message;
  if (legsRootMessage) clientItems.push({ message: legsRootMessage });
  fields.forEach((_, index) => {
    for (const name of LEG_FIELD_ORDER) {
      const message = errors.legs?.[index]?.[name]?.message;
      if (message) {
        clientItems.push({
          message,
          fieldId: fieldIdFromPath(`legs.${index}.${name}`),
        });
      }
    }
  });
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
      current={stepNumber("itinerary")}
      back={
        <Link to={stepPath(claim.id, "trip")} className="text-sm text-link underline">
          Back to Trip
        </Link>
      }
      taskList={<TaskList sections={buildTaskSections(claim)} />}
    >
      <UnsavedChangesGuard
        shouldBlock={() => form.formState.isDirty && !leavingRef.current}
      />
      <div className="flex flex-col gap-6">
        {summaryItems.length > 0 ? (
          <ErrorSummary
            key={`${form.formState.submitCount}-${save.failureCount}`}
            errors={summaryItems}
          />
        ) : null}

        <form onSubmit={onSubmit} noValidate className="flex flex-col gap-6">
          {fields.map((field, index) => (
            <fieldset
              key={field.id}
              className="flex flex-col gap-4 rounded-md border border-border bg-surface p-4"
            >
              <legend className="px-1 text-base font-bold text-text">
                Leg {index + 1}
              </legend>
              <div className="grid gap-4 sm:grid-cols-2">
                <FormField
                  id={`legs-${index}-leg_date`}
                  label="Date"
                  type="date"
                  required
                  error={errors.legs?.[index]?.leg_date?.message}
                  {...form.register(`legs.${index}.leg_date`)}
                />
                <FormField
                  id={`legs-${index}-place`}
                  label="Place"
                  required
                  error={errors.legs?.[index]?.place?.message}
                  {...form.register(`legs.${index}.place`)}
                />
                <SelectField
                  id={`legs-${index}-destination_region_code`}
                  label="Region"
                  help="Leave blank to use the trip's destination region."
                  options={regionOptions}
                  placeholder="Same as the trip"
                  error={errors.legs?.[index]?.destination_region_code?.message}
                  {...form.register(`legs.${index}.destination_region_code`)}
                />
                <SelectField
                  id={`legs-${index}-transport_mode`}
                  label="Transport mode"
                  options={TRANSPORT_MODE_OPTIONS}
                  placeholder="Select a mode"
                  required
                  error={errors.legs?.[index]?.transport_mode?.message}
                  {...form.register(`legs.${index}.transport_mode`)}
                />
                <FormField
                  id={`legs-${index}-time_depart`}
                  label="Time of departure"
                  help="24-hour clock, e.g. 08:30."
                  error={errors.legs?.[index]?.time_depart?.message}
                  {...form.register(`legs.${index}.time_depart`)}
                />
                <FormField
                  id={`legs-${index}-time_arrive`}
                  label="Time of arrival"
                  help="24-hour clock, e.g. 17:00."
                  error={errors.legs?.[index]?.time_arrive?.message}
                  {...form.register(`legs.${index}.time_arrive`)}
                />
                <FormField
                  id={`legs-${index}-fare`}
                  label="Fare"
                  help="From the official receipt. Government-vehicle legs claim no fare."
                  inputMode="decimal"
                  error={errors.legs?.[index]?.fare?.message}
                  {...form.register(`legs.${index}.fare`)}
                />
              </div>
              <div className="flex flex-col gap-1">
                <CheckboxField
                  id={`legs-${index}-lodging_provided`}
                  label="Lodging was provided by the host"
                  {...form.register(`legs.${index}.lodging_provided`)}
                />
                <CheckboxField
                  id={`legs-${index}-meals_provided`}
                  label="Meals were provided by the host"
                  {...form.register(`legs.${index}.meals_provided`)}
                />
              </div>
              {fields.length > 1 ? (
                <div>
                  <Button variant="secondary" onClick={() => remove(index)}>
                    Remove leg {index + 1}
                  </Button>
                </div>
              ) : null}
            </fieldset>
          ))}

          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={() => append(emptyLeg())}>
              Add another leg
            </Button>
            <Button type="submit" loading={save.isPending}>
              {fromReview ? "Save and return to review" : "Continue"}
            </Button>
          </div>
        </form>
      </div>
    </WizardPage>
  );
}
