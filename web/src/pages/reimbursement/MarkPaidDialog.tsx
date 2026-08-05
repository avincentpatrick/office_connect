import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  markPaid,
  reimbKeys,
  type ClaimDetail,
} from "../../api/reimbursement";
import { ApiError } from "../../api/http";
import { Callout } from "../../components/Callout/Callout";
import { FormDialog } from "../../components/Dialog/FormDialog";
import { ErrorSummary } from "../../components/ErrorSummary/ErrorSummary";
import type { ErrorSummaryItem } from "../../components/ErrorSummary/ErrorSummary";
import { FormField } from "../../components/FormField/FormField";
import { toast } from "../../components/Toast/toast-bus";
import { formatPeso } from "../../lib/format";
import { serverFieldErrors } from "../../lib/form-errors";
import {
  MARK_PAID_FIELDS,
  manilaToday,
  markPaidSchema,
  toMarkPaidBody,
  type MarkPaidFormValues,
} from "./fms-forms";

/**
 * Closing a claim as paid (R-7-events, spec §6.1 row 8) — the last thing anyone
 * does to a travel claim, and the one act the whole module exists to reach.
 *
 * It is a FORM rather than a confirm because the state records data: spec §6.1
 * row 8 says "terminal (admin records payout ref)", and until this increment
 * the transition was a bare approve that recorded nothing at all.
 *
 * The dialog is blunt about irreversibility, twice over — in the description
 * and beside the reference field. That is not decoration: `paid_closed` is
 * read-only for everyone afterwards and there is no route that can amend a
 * payment reference on a closed claim, so a wrong entry here is permanent. An
 * Admin Officer who does not have the reference yet has an honest alternative,
 * and the server's refusal names it: relay "Payment processing" instead.
 */
export function MarkPaidDialog({
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
  const [blocked, setBlocked] = useState<string | null>(null);

  const form = useForm<MarkPaidFormValues>({
    resolver: zodResolver(markPaidSchema),
    // Manila's today, not the browser's: the server validates against Manila,
    // so a browser elsewhere would otherwise prefill a date it refuses.
    defaultValues: { payout_ref: "", paid_on: manilaToday() },
  });

  const pay = useMutation({
    mutationFn: (values: MarkPaidFormValues) =>
      markPaid(claim.id, toMarkPaidBody(values, claim.row_version)),
    onSuccess: (updated) => {
      form.reset();
      setBlocked(null);
      setServerErrors([]);
      onOpenChange(false);
      queryClient.setQueryData(reimbKeys.claim(claim.id), updated);
      void queryClient.invalidateQueries({ queryKey: reimbKeys.myWork() });
      void queryClient.invalidateQueries({ queryKey: reimbKeys.queues() });
      void queryClient.invalidateQueries({
        queryKey: reimbKeys.timeline(claim.id),
      });
      toast(`${claim.ref_no ?? "The claim"} is closed as paid.`, "success");
    },
    onError: (error) => {
      setBlocked(null);
      setServerErrors([]);
      if (!(error instanceof ApiError)) {
        toast("Something went wrong. Please try again.");
        return;
      }
      if (error.status === 409) {
        // Already paid, moved out of FMS, or a stale CAS token — all
        // whole-record refusals. Nothing was written (the reference and the
        // transition are one transaction), so the retry after a reload is safe.
        setBlocked(error.message);
        void queryClient.invalidateQueries({
          queryKey: reimbKeys.claim(claim.id),
        });
        return;
      }
      setServerErrors(serverFieldErrors(error, form.setError, MARK_PAID_FIELDS));
    },
  });

  const amount = claim.totals?.grand ? formatPeso(claim.totals.grand) : null;

  return (
    <FormDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Mark this claim paid"
      description={
        amount
          ? `Record how FMS paid the ${amount} on this claim. This closes it for good — it becomes read-only for everyone, including you.`
          : "Record how FMS paid this claim. This closes it for good — it becomes read-only for everyone, including you."
      }
      submitLabel="Record payment & close"
      busy={pay.isPending}
      onSubmit={form.handleSubmit((values) => pay.mutate(values))}
    >
      {serverErrors.length > 0 ? <ErrorSummary errors={serverErrors} /> : null}
      {blocked ? (
        <Callout status="blocked" title="Cannot close this claim" live="polite">
          {blocked}
        </Callout>
      ) : null}

      <FormField
        id="payout_ref"
        label="Payment reference"
        required
        help="The ADA, LDDAP or cheque reference FMS gave you. Nothing can add it later, so leave this open and relay “Payment processing” if you do not have it yet."
        error={form.formState.errors.payout_ref?.message}
        {...form.register("payout_ref")}
      />
      <FormField
        id="paid_on"
        label="Date FMS paid"
        type="date"
        required
        help="The date the money moved, not today's date if they differ."
        error={form.formState.errors.paid_on?.message}
        {...form.register("paid_on")}
      />
    </FormDialog>
  );
}

/**
 * What a paid claim says afterwards — the receipt the claimant and any future
 * auditor read (R-7-events).
 *
 * The same doctrine `SettlementOutcome` follows one chain over: how the money
 * came out is a fact about the RECORD, not a status, so it renders as a panel
 * beside the claim rather than as a chip. The reference is the whole point of
 * the panel: it is what a traveller quotes to FMS or their bank when the credit
 * has not appeared, and they can look it up nowhere else.
 */
export function PaidOutcome({ claim }: { claim: ClaimDetail }) {
  if (claim.status !== "paid_closed") return null;

  const amount = claim.totals?.grand ? formatPeso(claim.totals.grand) : null;
  return (
    <Callout status="done" title={amount ? `${amount} paid` : "Paid"}>
      <p>
        FMS paid this claim
        {claim.paid_on ? ` on ${claim.paid_on}` : ""}
        {claim.payout_ref ? ` under reference ${claim.payout_ref}` : ""}. The
        claim is closed and nothing further is needed.
      </p>
    </Callout>
  );
}
