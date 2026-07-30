/**
 * Server-error → form-error mapping (R-2-wizard). Pydantic 422s carry
 * `ValidationDetail[]` in `error.details`; each `loc` maps onto a
 * react-hook-form path (drop the leading "body", join with "."). Business
 * errors (reimb_* slugs) carry no loc and surface as page-level summary items
 * — the message copy says what to fix ("never block without a path").
 *
 * Binding DOM-id convention for every wizard field: id = the RHF path with
 * dots → dashes (`dpo_no`, `legs-0-fare`) so ErrorSummary anchors resolve
 * mechanically. Inline wording == summary wording by construction (GOV.UK).
 */

import type { FieldValues, Path, UseFormSetError } from "react-hook-form";
import { ApiError } from "../api/http";
import type { ValidationDetail } from "../api/types";
import type { ErrorSummaryItem } from "../components/ErrorSummary/ErrorSummary";

export function fieldIdFromPath(path: string): string {
  return path.replaceAll(".", "-");
}

function isValidationDetails(details: unknown): details is ValidationDetail[] {
  return (
    Array.isArray(details) &&
    details.length > 0 &&
    details.every(
      (d) =>
        typeof d === "object" &&
        d !== null &&
        Array.isArray((d as ValidationDetail).loc) &&
        typeof (d as ValidationDetail).msg === "string",
    )
  );
}

/**
 * Map an API failure onto the form. `knownFields` lists the step's RHF paths;
 * a bare array name (e.g. "legs") whitelists every `legs.<i>.<field>` path.
 * Returns the ErrorSummary items (anchored where a field matched).
 */
export function serverFieldErrors<T extends FieldValues>(
  error: unknown,
  setError: UseFormSetError<T>,
  knownFields: ReadonlySet<string>,
): ErrorSummaryItem[] {
  if (!(error instanceof ApiError)) {
    return [{ message: "Something went wrong. Please try again." }];
  }
  if (!isValidationDetails(error.details)) {
    return [{ message: error.message }];
  }

  const items: ErrorSummaryItem[] = [];
  for (const detail of error.details) {
    const parts = detail.loc[0] === "body" ? detail.loc.slice(1) : detail.loc;
    const path = parts.join(".");
    const known =
      path !== "" &&
      (knownFields.has(path) || knownFields.has(String(parts[0] ?? "")));
    if (known) {
      setError(path as Path<T>, { type: "server", message: detail.msg });
      items.push({ message: detail.msg, fieldId: fieldIdFromPath(path) });
    } else {
      items.push({ message: detail.msg });
    }
  }
  return items.length > 0 ? items : [{ message: error.message }];
}
