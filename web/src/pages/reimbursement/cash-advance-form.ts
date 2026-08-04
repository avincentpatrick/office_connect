/**
 * Cash-advance form schema + wire mapper (R-6-clock).
 *
 * Shape only, exactly like `claim-forms.ts`: required/format/date-order. Every
 * business rule stays server-side — the PD 1445 §89 one-advance-at-a-time block
 * and the deadline arithmetic are the server's, and re-implementing either here
 * would create a second answer that can disagree with the first.
 *
 * Note what is deliberately ABSENT from the form: `deadline_date`,
 * `deadline_basis` and `status`. The clock is computed and pinned server-side
 * (api-standards §2) — a client that could post a deadline could post one COA
 * never gave.
 */

import { z } from "zod";
import type { CashAdvanceInput } from "../../api/reimbursement";

const MONEY_RE = /^\d+(\.\d{1,2})?$/;

export const cashAdvanceSchema = z
  .object({
    claimant_id: z
      .string()
      .min(1, "Enter the claimant's staff ID")
      .regex(/^\d+$/, "Staff ID must be a number"),
    amount: z
      .string()
      .min(1, "Enter the advance amount")
      .regex(MONEY_RE, "Enter an amount like 5000.00")
      // Format-checked as a STRING and never parsed into a float — the money
      // prohibition (tech-stack §4). The server rejects zero with its own
      // message; this only catches the shape.
      .refine((v) => Number(v) > 0, "The amount must be more than ₱0.00"),
    dv_no: z.string(),
    dv_date: z.union([z.iso.date(), z.literal("")]),
    dpo_no: z.string(),
    date_return: z.union([z.iso.date(), z.literal("")]),
  })
  .refine(
    (values) =>
      values.dv_date === "" ||
      values.date_return === "" ||
      values.date_return >= values.dv_date,
    {
      // Wording matches `errors.cash_advance_dates_invalid` server-side
      // (ui-standards §3.14 — one rule, one sentence).
      message: "The return date is before the DV date — check the dates",
      path: ["date_return"],
    },
  );

export type CashAdvanceFormValues = z.infer<typeof cashAdvanceSchema>;

/** RHF paths this form owns, for the 422 `loc` → field mapper. */
export const CASH_ADVANCE_FIELDS: ReadonlySet<string> = new Set([
  "claimant_id",
  "amount",
  "dv_no",
  "dv_date",
  "dpo_no",
  "date_return",
]);

/** Summary ordering — the visual order of the form (GOV.UK error summary). */
export const CASH_ADVANCE_FIELD_ORDER = [
  "claimant_id",
  "amount",
  "dv_no",
  "dv_date",
  "dpo_no",
  "date_return",
] as const;

/** Empty optional strings become `null`, so "not recorded" is not "". */
export function toCashAdvanceBody(
  values: CashAdvanceFormValues,
): CashAdvanceInput {
  const blankToNull = (v: string) => (v === "" ? null : v);
  return {
    claimant_id: Number(values.claimant_id),
    amount: values.amount,
    dv_no: blankToNull(values.dv_no),
    dv_date: blankToNull(values.dv_date),
    dpo_no: blankToNull(values.dpo_no),
    date_return: blankToNull(values.date_return),
  };
}
