/**
 * Module query hooks (R-2-wizard) — thin wrappers pairing `reimbKeys` with the
 * typed client. 403/404 never retry (they're answers, not blips).
 */

import { useQuery } from "@tanstack/react-query";
import {
  fetchClaim,
  fetchMyWork,
  fetchRegions,
  reimbKeys,
} from "../../api/reimbursement";

export function parseClaimId(raw: string | undefined): number | null {
  if (raw === undefined || !/^\d+$/.test(raw)) return null;
  const id = Number(raw);
  return Number.isSafeInteger(id) && id > 0 ? id : null;
}

export function useClaim(id: number | null) {
  return useQuery({
    queryKey: reimbKeys.claim(id ?? -1),
    queryFn: () => fetchClaim(id as number),
    enabled: id !== null,
    retry: false,
  });
}

export function useMyWork() {
  return useQuery({ queryKey: reimbKeys.myWork(), queryFn: fetchMyWork });
}

export function useRegions() {
  return useQuery({
    queryKey: reimbKeys.regions(),
    queryFn: fetchRegions,
    staleTime: 5 * 60_000, // reference data
  });
}
