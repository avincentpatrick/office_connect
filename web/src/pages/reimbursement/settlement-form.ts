/**
 * Settlement form schema + wire mapper (R-6-liq-settle).
 *
 * Shape only, exactly like `cash-advance-form.ts`. The one rule that IS here —
 * "an OR number needs its date, and vice versa" — is shape, not business: a
 * half-entered receipt is not a receipt. Everything else stays server-side.
 *
 * Note what is deliberately ABSENT: the settlement MODE and the amount as an
 * input. Both are the server's (`per_diem.settle`), and a client that could
 * post "this was a refund of ₱1,266" could post a refund that never happened.
 * The refund figure travels one way only — the server sends it, the form
 * DISPLAYS it, and it goes back untouched as an echo so a stale screen is
 * caught before it files a receipt against the wrong number.
 */

import { z } from "zod";
import type { SettlementInput } from "../../api/reimbursement";

export const settlementSchema = z
  .object({
    or_no: z.string(),
    or_date: z.union([z.iso.date(), z.literal("")]),
  })
  .refine((v) => !(v.or_no.trim() && v.or_date === ""), {
    message: "Enter the date on the official receipt",
    path: ["or_date"],
  })
  .refine((v) => !(v.or_date !== "" && !v.or_no.trim()), {
    message: "Enter the official receipt number",
    path: ["or_no"],
  });

export type SettlementFormValues = z.infer<typeof settlementSchema>;

/** RHF paths this form owns, for the 422 `loc` → field mapper. */
export const SETTLEMENT_FIELDS: ReadonlySet<string> = new Set([
  "or_no",
  "or_date",
]);

/**
 * Empty strings become `null`, so "not recorded" is not "". `refund_amount` is
 * echoed back verbatim as the server sent it — never re-derived, never
 * reformatted (the money prohibition: 2-dp strings, in and out).
 */
export function toSettlementBody(
  values: SettlementFormValues,
  refundAmount: string | null,
): SettlementInput {
  const blankToNull = (v: string) => (v.trim() === "" ? null : v.trim());
  return {
    or_no: blankToNull(values.or_no),
    or_date: values.or_date === "" ? null : values.or_date,
    refund_amount: refundAmount,
  };
}
