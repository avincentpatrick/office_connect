import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router";
import {
  reimbKeys,
  settleClaim,
  type ClaimDetail,
} from "../../api/reimbursement";
import { ApiError } from "../../api/http";
import { Button } from "../../components/Button/Button";
import { Callout } from "../../components/Callout/Callout";
import { FormDialog } from "../../components/Dialog/FormDialog";
import { ErrorSummary } from "../../components/ErrorSummary/ErrorSummary";
import type { ErrorSummaryItem } from "../../components/ErrorSummary/ErrorSummary";
import { FormField } from "../../components/FormField/FormField";
import { toast } from "../../components/Toast/toast-bus";
import { formatPeso } from "../../lib/format";
import { serverFieldErrors } from "../../lib/form-errors";
import {
  SETTLEMENT_FIELDS,
  settlementSchema,
  toSettlementBody,
  type SettlementFormValues,
} from "./settlement-form";

/**
 * Recording a settlement (R-6-liq-settle, spec §6.2) — Accounting's last act on
 * a liquidation, and the one that closes the cash advance.
 *
 * The receipt fields appear ONLY when the server says money is coming back.
 * That is not a convenience: an official receipt on a settlement that refunded
 * nothing is a receipt for a payment that never happened, and the server
 * refuses one. Rendering the inputs regardless would invite an operator to fill
 * a box whose only possible outcome is a 422.
 *
 * Which branch this is, is read from `totals` — the server's figures, never a
 * subtraction done here (the money prohibition).
 */
export function SettlementDialog({
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
  // A stale screen (`reimb_refund_amount_mismatch`) or a repeat tap
  // (`reimb_settlement_already_recorded`) is a whole-record refusal, not a field
  // problem — anchoring it to an input would send the operator to fix the wrong
  // thing. It renders as a Callout above the form, the §89 precedent.
  const [blocked, setBlocked] = useState<string | null>(null);

  // Read off the server's figures; never a subtraction done here. "0.00" is a
  // truthy STRING, which is exactly the bug `_dv32_body.html.j2` carried on the
  // print side — compare the value, never its truthiness.
  const toRefund = claim.totals?.to_refund ?? null;
  const toReimburse = claim.totals?.to_reimburse ?? null;
  const refund = toRefund !== null && toRefund !== "0.00" ? toRefund : null;
  const owed =
    toReimburse !== null && toReimburse !== "0.00" ? toReimburse : null;
  const isRefund = refund !== null;

  const form = useForm<SettlementFormValues>({
    resolver: zodResolver(settlementSchema),
    defaultValues: { or_no: "", or_date: "" },
  });

  const settle = useMutation({
    mutationFn: (values: SettlementFormValues) =>
      settleClaim(claim.id, toSettlementBody(values, refund)),
    onSuccess: (updated) => {
      form.reset();
      setBlocked(null);
      setServerErrors([]);
      onOpenChange(false); // FormDialog's caller closes on success
      queryClient.setQueryData(reimbKeys.claim(claim.id), updated);
      void queryClient.invalidateQueries({ queryKey: reimbKeys.myWork() });
      void queryClient.invalidateQueries({ queryKey: reimbKeys.cashAdvances() });
      void queryClient.invalidateQueries({
        queryKey: reimbKeys.timeline(claim.id),
      });
      toast(`${claim.ref_no ?? "The liquidation"} is settled.`, "success");
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
      if (error.code === "reimb_refund_amount_mismatch") {
        setBlocked(error.message);
        void queryClient.invalidateQueries({
          queryKey: reimbKeys.claim(claim.id),
        });
        return;
      }
      setServerErrors(serverFieldErrors(error, form.setError, SETTLEMENT_FIELDS));
    },
  });

  const description =
    refund !== null
      ? `${formatPeso(refund)} is refundable. Record the DOH official receipt that evidences it — this closes the cash advance.`
      : owed !== null
        ? `The advance was fully spent and ${formatPeso(owed)} is still owed to the traveller. This closes the cash advance; the traveller claims the difference on a separate voucher.`
        : "The advance was spent exactly. Nothing is refundable and nothing is owed — this closes the cash advance.";

  return (
    <FormDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Record the settlement"
      description={description}
      // Distinct from the trigger's "Record settlement" on purpose: the trigger
      // opens a form, this one performs the act — and naming the consequence
      // (§3.10) is what tells an operator that this also CLOSES the advance.
      submitLabel="Record and close"
      busy={settle.isPending}
      onSubmit={form.handleSubmit((values) => settle.mutate(values))}
    >
      {serverErrors.length > 0 ? <ErrorSummary errors={serverErrors} /> : null}
      {blocked ? (
        <Callout status="blocked" title="Cannot record this settlement" live="polite">
          {blocked}
        </Callout>
      ) : null}

      {isRefund ? (
        <>
          <FormField
            id="or_no"
            label="Official receipt number"
            required
            help="The DOH OR issued when the traveller refunded the excess."
            error={form.formState.errors.or_no?.message}
            {...form.register("or_no")}
          />
          <FormField
            id="or_date"
            label="Official receipt date"
            type="date"
            required
            error={form.formState.errors.or_date?.message}
            {...form.register("or_date")}
          />
        </>
      ) : (
        <Callout status="waiting" title="No receipt to record">
          Nothing came back from this advance, so there is no official receipt.
        </Callout>
      )}
    </FormDialog>
  );
}

/**
 * What a settled liquidation says afterwards (spec §6.3's derived-badge
 * doctrine: money facts live on the record, not in the status column).
 *
 * The over-advance branch is the only one that asks anything of anyone, and it
 * asks the TRAVELLER — which is why the button is theirs, gated on the
 * server-sent action set rather than a role the client guessed.
 */
export function SettlementOutcome({
  claim,
  onSpawn,
  spawning = false,
  canSpawn = false,
}: {
  claim: ClaimDetail;
  onSpawn?: () => void;
  spawning?: boolean;
  canSpawn?: boolean;
}) {
  const advance = claim.cash_advance;
  if (!advance?.settlement_mode) return null;

  if (advance.settlement_mode === "refund") {
    return (
      <Callout status="done" title="Settled — excess refunded">
        <p>
          {advance.refund_amount ? formatPeso(advance.refund_amount) : "The excess"}{" "}
          was refunded
          {advance.refund_or_no
            ? ` against official receipt ${advance.refund_or_no}`
            : ""}
          . The cash advance is closed.
        </p>
      </Callout>
    );
  }

  if (advance.settlement_mode === "exact") {
    return (
      <Callout status="done" title="Settled">
        <p>
          The cash advance was spent exactly and is closed. Nothing is
          refundable and nothing is owed.
        </p>
      </Callout>
    );
  }

  const raw = claim.totals?.to_reimburse ?? null;
  const owed = raw !== null && raw !== "0.00" ? formatPeso(raw) : "The balance";
  return (
    <Callout status="warn" title={`${owed} is due you`}>
      <p>
        You spent more than the cash advance covered. The advance is closed;
        claim the difference on a separate voucher.
      </p>
      {claim.spawned_claim ? (
        <p className="mt-2">
          Claimed under{" "}
          <Link
            className="underline"
            to={`/reimbursement/claims/${claim.spawned_claim.claim_id}`}
          >
            {claim.spawned_claim.ref_no ??
              `claim #${claim.spawned_claim.claim_id}`}
          </Link>{" "}
          ({claim.spawned_claim.status_label}).
        </p>
      ) : canSpawn && onSpawn ? (
        // Honest copy: the spawn is a pre-filled DRAFT, not a finished claim.
        // The traveller still walks it through the wizard and re-attaches the
        // travel order and the certificate of travel completed — carrying the
        // evidence across is a recorded deferral, so the button must not
        // promise it (§9.1 principle 3).
        <div className="mt-2">
          <Button variant="secondary" onClick={onSpawn} loading={spawning}>
            {`Start your claim for ${owed}`}
          </Button>
        </div>
      ) : null}
    </Callout>
  );
}
