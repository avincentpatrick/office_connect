/**
 * Module query hooks (R-2-wizard) — thin wrappers pairing `reimbKeys` with the
 * typed client. 403/404 never retry (they're answers, not blips).
 */

import { useQuery } from "@tanstack/react-query";
import {
  fetchCashAdvance,
  fetchCashAdvances,
  fetchChecklist,
  fetchClaim,
  fetchClaimQueue,
  fetchMyWork,
  fetchRegions,
  fetchReturnReasons,
  fetchTimeline,
  reimbKeys,
  type ClaimQueueFilters,
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

export function useTimeline(id: number | null) {
  return useQuery({
    queryKey: reimbKeys.timeline(id ?? -1),
    queryFn: () => fetchTimeline(id as number),
    enabled: id !== null,
    retry: false,
  });
}

export function useReturnReasons() {
  return useQuery({
    queryKey: reimbKeys.returnReasons(),
    queryFn: fetchReturnReasons,
    staleTime: 5 * 60_000, // seeded taxonomy
  });
}

export function useChecklist(id: number | null) {
  return useQuery({
    queryKey: reimbKeys.checklist(id ?? -1),
    queryFn: () => fetchChecklist(id as number),
    enabled: id !== null,
    retry: false,
  });
}

/**
 * The caller's own cash advances (R-6-clock), or a specific claimant's for an
 * actor holding `reimb.cash_advance.manage`. Omitting `claimantId` means "mine"
 * — resolved server-side from the session's staff link, never from a client id.
 */
export function useCashAdvances(claimantId?: number) {
  return useQuery({
    queryKey: reimbKeys.cashAdvances(claimantId),
    queryFn: () => fetchCashAdvances(claimantId),
    retry: false,
  });
}

export function useCashAdvance(id: number | null) {
  return useQuery({
    queryKey: reimbKeys.cashAdvance(id ?? -1),
    queryFn: () => fetchCashAdvance(id as number),
    enabled: id !== null,
    retry: false,
  });
}

/**
 * The oversight queue (R-7-queue) — other people's claims, scoped server-side.
 *
 * `retry: false` matters more here than anywhere else in this file: an actor
 * who oversees nobody gets a 403, and that is a settled answer the page renders
 * as an explanation, not a blip worth asking about three times.
 */
export function useClaimQueue(filters: ClaimQueueFilters = {}) {
  return useQuery({
    queryKey: reimbKeys.queue(filters),
    queryFn: () => fetchClaimQueue(filters),
    retry: false,
  });
}
