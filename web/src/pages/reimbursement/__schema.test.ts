import { describe, expect, it } from "vitest";
import { cashAdvanceSchema } from "./cash-advance-form";
describe("schema", () => {
  it("rejects empties", () => {
    const r = cashAdvanceSchema.safeParse({
      claimant_id: "", amount: "", dv_no: "", dv_date: "", dpo_no: "", date_return: "",
    });
    console.log(JSON.stringify(r.success ? "OK" : r.error.issues));
    expect(r.success).toBe(false);
  });
});
