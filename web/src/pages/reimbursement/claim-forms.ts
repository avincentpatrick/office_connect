/**
 * Per-step zod schemas + form ⇄ wire mappers (R-2-wizard). Schemas validate
 * SHAPE only (required/format/date-order) — money and every business rule
 * stay server-side (tech-stack §4 hard prohibition; fares are format-checked
 * strings, never parsed or summed). Field DOM ids follow the binding
 * convention in lib/form-errors.ts: RHF path with dots → dashes.
 */

import { z } from "zod";
import type {
  ClaimDetail,
  ClaimPatch,
  FundSource,
  LegInput,
  TransportMode,
} from "../../api/reimbursement";

const TIME_RE = /^([01]\d|2[0-3]):[0-5]\d$/;
const MONEY_RE = /^\d+(\.\d{1,2})?$/;

export const TRANSPORT_MODE_OPTIONS: { value: TransportMode; label: string }[] = [
  { value: "plane", label: "Plane" },
  { value: "bus", label: "Bus" },
  { value: "boat", label: "Boat" },
  { value: "taxi", label: "Taxi" },
  { value: "ride_hail", label: "Ride hail" },
  { value: "gov_vehicle", label: "Government vehicle" },
  { value: "other", label: "Other" },
];

export const YES_NO_OPTIONS = [
  { value: "yes", label: "Yes" },
  { value: "no", label: "No" },
];

// --- Step 1: Trip ------------------------------------------------------------

export const tripSchema = z
  .object({
    dpo_no: z.string().min(1, "Enter the DPO number"),
    dpo_date: z.iso.date("Enter the DPO date"),
    purpose: z.string().min(1, "Enter the purpose of the trip"),
    destination: z.string().min(1, "Enter the destination"),
    destination_region_code: z.string().min(1, "Select the destination region"),
    date_depart: z.iso.date("Enter the departure date"),
    date_return: z.iso.date("Enter the return date"),
    is_within_50km: z.string().min(1, "Select yes or no for the 50 km question"),
    overnight_stay: z.string().min(1, "Select yes or no for the overnight question"),
  })
  .refine((values) => values.date_return >= values.date_depart, {
    message: "The return date must be on or after the departure date",
    path: ["date_return"],
  });

export type TripFormValues = z.infer<typeof tripSchema>;

export const TRIP_FIELD_ORDER = [
  "dpo_no",
  "dpo_date",
  "purpose",
  "destination",
  "destination_region_code",
  "date_depart",
  "date_return",
  "is_within_50km",
  "overnight_stay",
] as const;

export const TRIP_KNOWN_FIELDS: ReadonlySet<string> = new Set(TRIP_FIELD_ORDER);

export function toTripFormValues(claim: ClaimDetail): TripFormValues {
  // The attestation columns are NOT NULL (default false), so "never answered"
  // is indistinguishable from "answered no" in the data. Proxy: while the Trip
  // step is untouched, present the radios UNANSWERED (an attestation must be a
  // conscious answer — GOV.UK); once any trip field is saved, mirror storage.
  const tripUntouched = [
    claim.dpo_no,
    claim.dpo_date,
    claim.purpose,
    claim.destination,
    claim.destination_region_code,
    claim.date_depart,
    claim.date_return,
  ].every((value) => value === null);
  return {
    dpo_no: claim.dpo_no ?? "",
    dpo_date: claim.dpo_date ?? "",
    purpose: claim.purpose ?? "",
    destination: claim.destination ?? "",
    destination_region_code: claim.destination_region_code ?? "",
    date_depart: claim.date_depart ?? "",
    date_return: claim.date_return ?? "",
    is_within_50km: tripUntouched ? "" : claim.is_within_50km ? "yes" : "no",
    overnight_stay: tripUntouched ? "" : claim.overnight_stay ? "yes" : "no",
  };
}

export function toTripPatch(values: TripFormValues): ClaimPatch {
  return {
    dpo_no: values.dpo_no,
    dpo_date: values.dpo_date,
    purpose: values.purpose,
    destination: values.destination,
    destination_region_code: values.destination_region_code,
    date_depart: values.date_depart,
    date_return: values.date_return,
    is_within_50km: values.is_within_50km === "yes",
    overnight_stay: values.overnight_stay === "yes",
  };
}

// --- Step 2: Itinerary --------------------------------------------------------

export const legSchema = z.object({
  /** Bookkeeping: the existing leg's server id (null = new row). Named legId —
   * useFieldArray reserves `id` for its own render keys. */
  legId: z.number().nullable(),
  leg_date: z.iso.date("Enter the leg date"),
  place: z.string().min(1, "Enter the place for this leg"),
  destination_region_code: z.string(),
  time_depart: z
    .string()
    .regex(TIME_RE, "Enter the departure time as HH:MM")
    .or(z.literal("")),
  time_arrive: z
    .string()
    .regex(TIME_RE, "Enter the arrival time as HH:MM")
    .or(z.literal("")),
  transport_mode: z.string().min(1, "Select the transport mode"),
  fare: z
    .string()
    .regex(MONEY_RE, "Enter the fare as an amount like 150.00")
    .or(z.literal("")),
  lodging_provided: z.boolean(),
  meals_provided: z.boolean(),
});

export const itinerarySchema = z.object({
  legs: z.array(legSchema).min(1, "Add at least one itinerary leg"),
});

export type LegFormValues = z.infer<typeof legSchema>;
export type ItineraryFormValues = z.infer<typeof itinerarySchema>;

export const LEG_FIELD_ORDER = [
  "leg_date",
  "place",
  "destination_region_code",
  "time_depart",
  "time_arrive",
  "transport_mode",
  "fare",
] as const;

export const ITINERARY_KNOWN_FIELDS: ReadonlySet<string> = new Set(["legs"]);

export function emptyLeg(): LegFormValues {
  return {
    legId: null,
    leg_date: "",
    place: "",
    destination_region_code: "",
    time_depart: "",
    time_arrive: "",
    transport_mode: "",
    fare: "",
    lodging_provided: false,
    meals_provided: false,
  };
}

export function toItineraryFormValues(claim: ClaimDetail): ItineraryFormValues {
  if (claim.legs.length === 0) return { legs: [emptyLeg()] };
  return {
    legs: claim.legs.map((leg) => ({
      legId: leg.id,
      leg_date: leg.leg_date ?? "",
      place: leg.place ?? "",
      destination_region_code: leg.destination_region_code ?? "",
      time_depart: leg.time_depart ?? "",
      time_arrive: leg.time_arrive ?? "",
      transport_mode: leg.transport_mode ?? "",
      fare: leg.fare ?? "",
      lodging_provided: leg.lodging_provided,
      meals_provided: leg.meals_provided,
    })),
  };
}

export function toLegInputs(values: ItineraryFormValues): LegInput[] {
  return values.legs.map((leg) => ({
    ...(leg.legId !== null ? { id: leg.legId } : {}),
    leg_date: leg.leg_date || null,
    place: leg.place || null,
    destination_region_code: leg.destination_region_code || null,
    time_depart: leg.time_depart || null,
    time_arrive: leg.time_arrive || null,
    transport_mode: (leg.transport_mode || null) as TransportMode | null,
    fare: leg.fare || null,
    lodging_provided: leg.lodging_provided,
    meals_provided: leg.meals_provided,
  }));
}

// --- Step 3: Money -------------------------------------------------------------

export const moneySchema = z.object({
  other_total: z
    .string()
    .regex(MONEY_RE, "Enter other expenses as an amount like 250.00")
    .or(z.literal("")),
  fund_source: z.string().min(1, "Select the fund source"),
});

export type MoneyFormValues = z.infer<typeof moneySchema>;

export const MONEY_FIELD_ORDER = ["other_total", "fund_source"] as const;

export const MONEY_KNOWN_FIELDS: ReadonlySet<string> = new Set(MONEY_FIELD_ORDER);

export const FUND_SOURCE_OPTIONS = [
  { value: "GF_ORS", label: "General Fund (ORS)" },
  { value: "TF_BUR", label: "Trust Fund (BUR)" },
];

export function toMoneyFormValues(claim: ClaimDetail): MoneyFormValues {
  return {
    other_total: claim.other_total === "0.00" ? "" : claim.other_total,
    fund_source: claim.fund_source ?? "",
  };
}

export function toMoneyPatch(values: MoneyFormValues): ClaimPatch {
  return {
    other_total: values.other_total === "" ? "0.00" : values.other_total,
    fund_source: values.fund_source as FundSource,
  };
}
