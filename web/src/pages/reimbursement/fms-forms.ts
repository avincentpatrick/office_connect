/**
 * The two FMS-leg forms — schema + wire mapper, shape only (R-7-events).
 *
 * Same contract as `settlement-form.ts`: what lives here is SHAPE ("a payment
 * reference is a non-empty string", "a date is a date"), never business. The
 * closed set of FMS statuses, whether the claim is even with FMS, and whether a
 * reference was already recorded are all the server's, and the server refuses
 * with sentences this layer never has to author.
 *
 * One rule is deliberately NOT here: the relay does not check that the status
 * you picked comes "after" the last one. Spec §6.1 row 6 says *any order, skips
 * allowed*, and a client-side sequence check would invent a rule the server
 * does not have — which is worse than no check, because the operator would be
 * blocked by a screen instead of corrected by a service.
 */

import { z } from "zod";
import type {
  ExternalEventInput,
  ExternalStatus,
  MarkPaidInput,
} from "../../api/reimbursement";

/**
 * The three relay options, in the order spec §6.1 row 6 lists them — a typical
 * journey, offered as a list of choices rather than a sequence to walk. Labels
 * mirror the server's `external.LABELS`; the server's own strings win wherever
 * one is available (the tracker, the rail, the queue row all read
 * `status_label`), and these exist because a radio group has to render before
 * any event exists to carry them.
 */
export const FMS_STATUS_OPTIONS: {
  value: ExternalStatus;
  label: string;
  description: string;
}[] = [
  {
    value: "with_budget",
    label: "With Budget",
    description: "Budget is checking the allotment and obligating the amount.",
  },
  {
    value: "with_accounting",
    label: "With Accounting",
    description: "Accounting is processing the voucher for payment.",
  },
  {
    value: "payment_processing",
    label: "Payment processing",
    description: "The payment itself is being prepared — ADA, cheque or credit.",
  },
];

export const fmsStatusSchema = z.object({
  status: z.enum(["with_budget", "with_accounting", "payment_processing"]),
  noted_by: z.string(),
  note: z.string(),
  event_date: z.union([z.iso.date(), z.literal("")]),
});

export type FmsStatusFormValues = z.infer<typeof fmsStatusSchema>;

/** RHF paths this form owns, for the 422 `loc` → field mapper. */
export const FMS_STATUS_FIELDS: ReadonlySet<string> = new Set([
  "status",
  "noted_by",
  "note",
  "event_date",
]);

export function toExternalEventBody(
  values: FmsStatusFormValues,
): ExternalEventInput {
  const blankToNull = (v: string) => (v.trim() === "" ? null : v.trim());
  return {
    status: values.status,
    noted_by: blankToNull(values.noted_by),
    note: blankToNull(values.note),
    event_date: values.event_date === "" ? null : values.event_date,
  };
}

/**
 * The payment reference is required, and required HERE as well as on the
 * server. Not belt-and-braces theatre: closing a claim is irreversible and
 * nothing can add the reference afterwards, so catching an empty box before the
 * request is the difference between a corrected field and a permanent gap in a
 * financial record.
 */
export const markPaidSchema = z.object({
  payout_ref: z
    .string()
    .trim()
    .min(1, "Enter the payment reference FMS gave you"),
  paid_on: z.iso.date("Enter the date FMS paid this claim"),
});

export type MarkPaidFormValues = z.infer<typeof markPaidSchema>;

export const MARK_PAID_FIELDS: ReadonlySet<string> = new Set([
  "payout_ref",
  "paid_on",
]);

export function toMarkPaidBody(
  values: MarkPaidFormValues,
  expectedVersion: number | null,
): MarkPaidInput {
  return {
    payout_ref: values.payout_ref.trim(),
    paid_on: values.paid_on,
    expected_version: expectedVersion,
  };
}

/**
 * Today in Manila as `YYYY-MM-DD`, for the payment date's default.
 *
 * Manila explicitly, not the browser's locale: the operator is typing a
 * Philippine calendar date off a Philippine desk, and the server validates
 * against Manila's today. A browser in another timezone would otherwise prefill
 * a date the server calls tomorrow and refuses.
 */
export function manilaToday(now: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Manila",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(now);
}
