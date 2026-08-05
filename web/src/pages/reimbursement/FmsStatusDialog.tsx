import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  recordExternalEvent,
  reimbKeys,
  type ClaimDetail,
} from "../../api/reimbursement";
import { ApiError } from "../../api/http";
import { Callout } from "../../components/Callout/Callout";
import { FormDialog } from "../../components/Dialog/FormDialog";
import { ErrorSummary } from "../../components/ErrorSummary/ErrorSummary";
import type { ErrorSummaryItem } from "../../components/ErrorSummary/ErrorSummary";
import { FormField } from "../../components/FormField/FormField";
import { RadioGroupField } from "../../components/RadioGroupField/RadioGroupField";
import { TextareaField } from "../../components/TextareaField/TextareaField";
import { toast } from "../../components/Toast/toast-bus";
import { serverFieldErrors } from "../../lib/form-errors";
import {
  FMS_STATUS_FIELDS,
  FMS_STATUS_OPTIONS,
  fmsStatusSchema,
  toExternalEventBody,
  type FmsStatusFormValues,
} from "./fms-forms";

/**
 * Relaying what FMS says (R-7-events, spec §6.1 row 6) — the Admin Officer
 * writing down a phone call so the claimant does not have to make one.
 *
 * **The three options are a list, not a sequence.** Spec §6.1 row 6 says "any
 * order/skips allowed", so nothing here is disabled because of what was relayed
 * last: FMS pays straight out of Budget, sends packets back to desks they
 * already left, and reports the same status twice in a week. Every one of those
 * is a legal relay, and greying out an option would invent a rule the server
 * does not have — blocking an operator with a screen instead of correcting them
 * with a service.
 *
 * The dialog says out loud that this moves nothing. An update that looked like
 * progress would be worse than no update: the ">10 working days with FMS" clock
 * on the queue counts from the hand-off, deliberately not from the last relay,
 * because "still with Budget" is news rather than movement.
 */
export function FmsStatusDialog({
  claim,
  open,
  onOpenChange,
}: {
  claim: ClaimDetail;
  open: boolean;
  onOpenChange: (next: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const [serverErrors, setServerErrors] = useState<ErrorSummaryItem[]>([]);
  // A claim that moved out of FMS under us (`reimb_external_event_wrong_state`)
  // is a whole-record refusal, not a field problem — anchoring it to an input
  // would send the operator to fix the wrong thing.
  const [blocked, setBlocked] = useState<string | null>(null);

  const form = useForm<FmsStatusFormValues>({
    resolver: zodResolver(fmsStatusSchema),
    defaultValues: {
      // Pre-selected from what FMS last said, because the commonest relay by
      // far is "still there" — and pre-selecting the NEXT status instead would
      // be the client asserting a sequence the server does not enforce.
      status: claim.latest_external?.status ?? "with_budget",
      noted_by: "",
      note: "",
      event_date: "",
    },
  });

  const relay = useMutation({
    mutationFn: (values: FmsStatusFormValues) =>
      recordExternalEvent(claim.id, toExternalEventBody(values)),
    onSuccess: (updated) => {
      form.reset();
      setBlocked(null);
      setServerErrors([]);
      onOpenChange(false);
      queryClient.setQueryData(reimbKeys.claim(claim.id), updated);
      void queryClient.invalidateQueries({
        queryKey: reimbKeys.timeline(claim.id),
      });
      void queryClient.invalidateQueries({ queryKey: reimbKeys.queues() });
      toast(
        `${claim.ref_no ?? "The claim"} is now ${updated.latest_external?.status_label ?? "updated"}.`,
        "success",
      );
    },
    onError: (error) => {
      setBlocked(null);
      setServerErrors([]);
      if (!(error instanceof ApiError)) {
        toast("Something went wrong. Please try again.");
        return;
      }
      if (error.status === 409) {
        setBlocked(error.message);
        // The claim moved under us — pull the truth back so the buttons
        // re-render honestly (the ClaimActions precedent).
        void queryClient.invalidateQueries({
          queryKey: reimbKeys.claim(claim.id),
        });
        return;
      }
      setServerErrors(
        serverFieldErrors(error, form.setError, FMS_STATUS_FIELDS),
      );
    },
  });

  return (
    <FormDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Update the FMS status"
      description="Record where the packet has got to inside FMS. This does not move the claim — it stays with FMS until they return it or pay it."
      submitLabel="Record update"
      busy={relay.isPending}
      onSubmit={form.handleSubmit((values) => relay.mutate(values))}
    >
      {serverErrors.length > 0 ? <ErrorSummary errors={serverErrors} /> : null}
      {blocked ? (
        <Callout status="blocked" title="Cannot record this update" live="polite">
          {blocked}
        </Callout>
      ) : null}

      <RadioGroupField
        id="status"
        legend="Where is the packet now?"
        help="Pick whichever is true — FMS works these in any order, and skipping one is normal."
        required
        error={form.formState.errors.status?.message}
        options={FMS_STATUS_OPTIONS.map((option) => ({
          value: option.value,
          label: option.label,
          hint: option.description,
        }))}
        {...form.register("status")}
      />
      <FormField
        id="noted_by"
        label="Who at FMS told you?"
        help="Optional. A name makes the next follow-up call much shorter."
        error={form.formState.errors.noted_by?.message}
        {...form.register("noted_by")}
      />
      <FormField
        id="event_date"
        label="When did FMS move it?"
        type="date"
        help="Optional. Leave blank if today, or if they did not say."
        error={form.formState.errors.event_date?.message}
        {...form.register("event_date")}
      />
      <TextareaField
        id="note"
        label="Anything else they said?"
        help="Optional. The claimant sees this on their tracker."
        error={form.formState.errors.note?.message}
        {...form.register("note")}
      />
    </FormDialog>
  );
}
