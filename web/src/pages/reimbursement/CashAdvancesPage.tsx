import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Banknote } from "lucide-react";
import { ApiError } from "../../api/http";
import {
  createCashAdvance,
  reimbKeys,
  type CashAdvance,
} from "../../api/reimbursement";
import { Button } from "../../components/Button/Button";
import { Callout } from "../../components/Callout/Callout";
import { FormDialog } from "../../components/Dialog/FormDialog";
import {
  ErrorSummary,
  type ErrorSummaryItem,
} from "../../components/ErrorSummary/ErrorSummary";
import { FormField } from "../../components/FormField/FormField";
import { toast } from "../../components/Toast/toast-bus";
import { ListPage } from "../../layouts/ListPage";
import { serverFieldErrors } from "../../lib/form-errors";
import { CashAdvanceCard } from "./CashAdvanceCard";
import {
  CASH_ADVANCE_FIELDS,
  cashAdvanceSchema,
  toCashAdvanceBody,
  type CashAdvanceFormValues,
} from "./cash-advance-form";
import { useCashAdvances } from "./use-claim";

/**
 * The Accounting-facing cash-advance register (R-6-clock).
 *
 * Recording an advance is Accounting's act, not the traveller's — ``dv_no`` and
 * ``dv_date`` are data only Accounting holds, and the PD 1445 §89
 * one-advance-at-a-time block is only worth having if the record it guards is
 * authoritative. The route is reachable by anyone; the SERVER decides what they
 * may do, and a 403 renders as a plain explanation rather than a blank page.
 */
export function CashAdvancesPage() {
  const [open, setOpen] = useState(false);
  const query = useCashAdvances();
  const queryClient = useQueryClient();

  const advances = query.data ?? [];
  const denied = query.error instanceof ApiError && query.error.status === 403;

  const recordButton = (
    <Button onClick={() => setOpen(true)}>Record a cash advance</Button>
  );

  if (query.isError) {
    return (
      <ListPage
        title="Cash advances"
        loading={false}
        isEmpty
        emptyState={{
          title: denied
            ? "You cannot view these cash advances"
            : "Cash advances could not load",
          description:
            query.error instanceof ApiError
              ? query.error.message
              : "Something went wrong. Please try again.",
        }}
      />
    );
  }

  return (
    // The dialog is a SIBLING of ListPage, not one of its children: ListPage
    // renders `children` only when the list is non-empty, and the empty state
    // is exactly where "Record a cash advance" matters most. Mounting it inside
    // made the empty-state button open nothing.
    <>
      <ListPage
        title="Cash advances"
        filters={
          advances.length > 0 ? (
            <div className="ml-auto">{recordButton}</div>
          ) : undefined
        }
        loading={query.isPending}
        isEmpty={advances.length === 0}
        emptyState={{
          icon: Banknote,
          title: "No cash advances recorded",
          description:
            "Record a travel cash advance to start its 30-day liquidation clock.",
          action: recordButton,
        }}
      >
        <ul className="flex flex-col gap-4">
          {advances.map((advance) => (
            <li key={advance.id}>
              <CashAdvanceCard advance={advance} />
            </li>
          ))}
        </ul>
      </ListPage>
      <RecordDialog
        open={open}
        onOpenChange={setOpen}
        onRecorded={(advance) => {
          void queryClient.invalidateQueries({
            queryKey: reimbKeys.cashAdvances(),
          });
          void queryClient.invalidateQueries({
            queryKey: reimbKeys.cashAdvances(advance.claimant_id),
          });
          toast("Cash advance recorded.");
        }}
      />
    </>
  );
}

function RecordDialog({
  open,
  onOpenChange,
  onRecorded,
}: {
  open: boolean;
  onOpenChange: (next: boolean) => void;
  onRecorded: (advance: CashAdvance) => void;
}) {
  const [serverErrors, setServerErrors] = useState<ErrorSummaryItem[]>([]);
  // The §89 refusal is a whole-record 409, not a field problem — it names an
  // OTHER advance, so anchoring it to an input would send the user to fix the
  // wrong thing. It renders as a Callout above the form instead.
  const [blocked, setBlocked] = useState<string | null>(null);

  const form = useForm<CashAdvanceFormValues>({
    resolver: zodResolver(cashAdvanceSchema),
    defaultValues: {
      claimant_id: "",
      amount: "",
      dv_no: "",
      dv_date: "",
      dpo_no: "",
      date_return: "",
    },
  });

  const record = useMutation({
    mutationFn: (values: CashAdvanceFormValues) =>
      createCashAdvance(toCashAdvanceBody(values)),
    onSuccess: (advance) => {
      form.reset();
      setBlocked(null);
      setServerErrors([]);
      onOpenChange(false); // FormDialog's caller closes on success (§3)
      onRecorded(advance);
    },
    onError: (error) => {
      setBlocked(null);
      setServerErrors([]);
      if (!(error instanceof ApiError)) {
        toast("Something went wrong. Please try again.");
        return;
      }
      if (error.code === "reimb_cash_advance_unliquidated") {
        setBlocked(error.message);
        return;
      }
      setServerErrors(
        serverFieldErrors(error, form.setError, CASH_ADVANCE_FIELDS),
      );
    },
  });

  return (
    <FormDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Record a cash advance"
      description="The 30-day COA liquidation clock starts from the return date."
      submitLabel="Record advance"
      busy={record.isPending}
      onSubmit={form.handleSubmit((values) => record.mutate(values))}
    >
      {serverErrors.length > 0 ? <ErrorSummary items={serverErrors} /> : null}
      {blocked ? (
        <Callout status="blocked" title="Cannot record this advance" live="polite">
          {blocked}
        </Callout>
      ) : null}

      <FormField
        id="claimant_id"
        label="Claimant staff ID"
        required
        error={form.formState.errors.claimant_id?.message}
        {...form.register("claimant_id")}
      />
      <FormField
        id="amount"
        label="Amount"
        required
        help="In pesos, e.g. 5000.00"
        error={form.formState.errors.amount?.message}
        {...form.register("amount")}
      />
      <FormField
        id="dv_no"
        label="DV number"
        error={form.formState.errors.dv_no?.message}
        {...form.register("dv_no")}
      />
      <FormField
        id="dv_date"
        label="DV date"
        type="date"
        error={form.formState.errors.dv_date?.message}
        {...form.register("dv_date")}
      />
      <FormField
        id="dpo_no"
        label="DPO number"
        error={form.formState.errors.dpo_no?.message}
        {...form.register("dpo_no")}
      />
      <FormField
        id="date_return"
        label="Date returned to official station"
        type="date"
        help="Leave blank until the trip is over — the clock starts from this date."
        error={form.formState.errors.date_return?.message}
        {...form.register("date_return")}
      />
    </FormDialog>
  );
}
