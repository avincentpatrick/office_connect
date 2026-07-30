import { describe, expect, it } from "vitest";
import { completeClaim } from "../../test/reimb-fixtures";
import {
  itinerarySchema,
  toItineraryFormValues,
  toLegInputs,
  tripSchema,
} from "./claim-forms";

const VALID_TRIP = {
  dpo_no: "DPO-1",
  dpo_date: "2026-06-20",
  purpose: "Site visit",
  destination: "Manila",
  destination_region_code: "13",
  date_depart: "2026-07-01",
  date_return: "2026-07-03",
  is_within_50km: "no",
  overnight_stay: "yes",
};

describe("tripSchema (shape only)", () => {
  it("accepts a complete trip", () => {
    expect(tripSchema.safeParse(VALID_TRIP).success).toBe(true);
  });

  it("rejects a return date before departure, pathed to date_return", () => {
    const result = tripSchema.safeParse({
      ...VALID_TRIP,
      date_depart: "2026-07-03",
      date_return: "2026-07-01",
    });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].path).toEqual(["date_return"]);
    }
  });
});

describe("itinerarySchema (shape only)", () => {
  const leg = toItineraryFormValues(completeClaim()).legs[0];

  it("rejects malformed times and fares by format, never by value", () => {
    expect(
      itinerarySchema.safeParse({ legs: [{ ...leg, time_depart: "25:00" }] }).success,
    ).toBe(false);
    expect(
      itinerarySchema.safeParse({ legs: [{ ...leg, fare: "12.345" }] }).success,
    ).toBe(false);
    expect(
      itinerarySchema.safeParse({ legs: [{ ...leg, fare: "999999.99" }] }).success,
    ).toBe(true); // magnitude is the server's business
  });

  it("requires at least one leg", () => {
    expect(itinerarySchema.safeParse({ legs: [] }).success).toBe(false);
  });
});

describe("toLegInputs", () => {
  it("maps legId to id, blanks to null, and drops nothing else", () => {
    const values = toItineraryFormValues(completeClaim());
    values.legs[1].time_depart = "";
    values.legs.push({
      legId: null,
      leg_date: "2026-07-02",
      place: "Fieldwork",
      destination_region_code: "",
      time_depart: "",
      time_arrive: "",
      transport_mode: "taxi",
      fare: "",
      lodging_provided: false,
      meals_provided: true,
    });
    const inputs = toLegInputs(values);
    expect(inputs[0].id).toBe(11);
    expect(inputs[1].time_depart).toBeNull();
    expect(inputs[2].id).toBeUndefined();
    expect(inputs[2].fare).toBeNull();
    expect(inputs[2].destination_region_code).toBeNull();
    expect(inputs[2].meals_provided).toBe(true);
  });
});
