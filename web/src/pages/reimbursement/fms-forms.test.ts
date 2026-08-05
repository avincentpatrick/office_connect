import { describe, expect, it } from "vitest";

import {
  FMS_STATUS_OPTIONS,
  fmsStatusSchema,
  manilaToday,
  markPaidSchema,
  toExternalEventBody,
  toMarkPaidBody,
} from "./fms-forms";

/**
 * R-7-events. What these forms validate is SHAPE; what they deliberately do NOT
 * validate is the thing a reader would most expect them to.
 */
describe("the FMS status relay form", () => {
  it("offers the three statuses as options, never as a sequence", () => {
    // Spec §6.1 row 6: "any order/skips allowed". Nothing in this module may
    // encode an order — a client-side sequence check would invent a rule the
    // server does not have, blocking an operator with a screen instead of
    // correcting them with a service.
    expect(FMS_STATUS_OPTIONS.map((o) => o.value)).toEqual([
      "with_budget",
      "with_accounting",
      "payment_processing",
    ]);
    // Every one of them is independently valid, whatever came before.
    for (const option of FMS_STATUS_OPTIONS) {
      const parsed = fmsStatusSchema.safeParse({
        status: option.value,
        noted_by: "",
        note: "",
        event_date: "",
      });
      expect(parsed.success).toBe(true);
    }
  });

  it("refuses a status the server does not track", () => {
    // `paid` included: it closes the claim and carries a payment reference, so
    // it goes through Mark paid, never the status dialog.
    for (const status of ["with_the_cashier", "paid"]) {
      const parsed = fmsStatusSchema.safeParse({
        status,
        noted_by: "",
        note: "",
        event_date: "",
      });
      expect(parsed.success).toBe(false);
    }
  });

  it("sends blanks as null, so 'not recorded' is not an empty string", () => {
    expect(
      toExternalEventBody({
        status: "with_budget",
        noted_by: "   ",
        note: "",
        event_date: "",
      }),
    ).toEqual({
      status: "with_budget",
      noted_by: null,
      note: null,
      event_date: null,
    });
  });

  it("trims the name it did get", () => {
    const body = toExternalEventBody({
      status: "with_accounting",
      noted_by: "  Ms. Reyes, Accounting  ",
      note: "Endorsed Friday.",
      event_date: "2026-07-03",
    });
    expect(body.noted_by).toBe("Ms. Reyes, Accounting");
    expect(body.event_date).toBe("2026-07-03");
  });
});

describe("the mark-paid form", () => {
  it("will not close a claim without a payment reference", () => {
    // Required here as well as on the server, and not as belt-and-braces:
    // closing a claim is irreversible and nothing can add the reference
    // afterwards, so catching an empty box before the request is the difference
    // between a corrected field and a permanent gap in a financial record.
    for (const payout_ref of ["", "   "]) {
      const parsed = markPaidSchema.safeParse({
        payout_ref,
        paid_on: "2026-07-03",
      });
      expect(parsed.success).toBe(false);
    }
  });

  it("states what to do rather than that something is invalid", () => {
    const parsed = markPaidSchema.safeParse({
      payout_ref: "",
      paid_on: "2026-07-03",
    });
    expect(parsed.success).toBe(false);
    if (!parsed.success) {
      expect(parsed.error.issues[0].message).toMatch(/Enter the payment/i);
    }
  });

  it("requires the payment date", () => {
    expect(
      markPaidSchema.safeParse({ payout_ref: "ADA-1", paid_on: "" }).success,
    ).toBe(false);
  });

  it("echoes the CAS token back untouched", () => {
    // The whole point of `expected_version`: a stale screen must be refused
    // rather than close a claim someone else already moved.
    expect(
      toMarkPaidBody(
        { payout_ref: "  ADA-2026-00417 ", paid_on: "2026-07-03" },
        7,
      ),
    ).toEqual({
      payout_ref: "ADA-2026-00417",
      paid_on: "2026-07-03",
      expected_version: 7,
    });
  });

  it("defaults the payment date to MANILA today, not the browser's", () => {
    // A browser in Honolulu is a day behind Manila. Defaulting to its today
    // would prefill a date the server calls tomorrow and refuses — so the
    // operator would meet a validation error on a field they never touched.
    // 2026-07-03 20:00 UTC is already the 4th in Manila (UTC+8).
    expect(manilaToday(new Date("2026-07-03T20:00:00Z"))).toBe("2026-07-04");
    expect(manilaToday(new Date("2026-07-03T10:00:00Z"))).toBe("2026-07-03");
  });
});
