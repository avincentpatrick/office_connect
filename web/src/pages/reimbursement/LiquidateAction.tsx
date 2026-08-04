import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router";

import { ApiError } from "../../api/http";
import {
  liquidateCashAdvance,
  reimbKeys,
  type CashAdvance,
} from "../../api/reimbursement";
import { Button } from "../../components/Button/Button";
import { toast } from "../../components/Toast/toast-bus";

/**
 * The cash-advance card's answer to its own countdown (R-6-liq-chain).
 *
 * Spec §9.3 step 1 promises *"if a matching open cash advance exists → offer
 * 'Liquidate that instead?'"*. It lands HERE rather than inside the New Claim
 * wizard because this is where a traveller actually meets the advance — the
 * ring counting down on their My-Work page is the moment the offer means
 * something, not a step-1 field they may never reach.
 *
 * The advance carries `liquidation_claim_id`, so this renders the START action
 * or the OPEN link from ONE response. Two requests could disagree, and the
 * disagreement would surface as a button that 409s — the R-4-screens doctrine
 * that the UI is never offered an action certain to fail.
 *
 * Starting is a button; opening is a LINK, because one changes server state and
 * the other navigates. Styling them alike would hide that difference from
 * exactly the users who most need it (ui-standards §3.1).
 *
 * `canStart` is the caller's honest answer to "are these the VIEWER's own
 * advances?" — true on My-Work, whose query resolves the claimant from the
 * caller's own staff link, and false on Accounting's register, which lists
 * other people's. It is not an authorization check (the server owns that, and
 * the endpoint is owner-only); it exists so a clerk is never shown a button
 * certain to 403. `/api/v1/me` carries no `staff_id`, so the component cannot
 * derive this itself without a core change wider than this increment.
 */
export function LiquidateAction({
  advance,
  canStart = true,
}: {
  advance: CashAdvance;
  canStart?: boolean;
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const start = useMutation({
    mutationFn: () => liquidateCashAdvance(advance.id),
    onSuccess: (claim) => {
      // The advance moved to `liquidation_started` and now names its claim, so
      // every list rendering it is stale.
      void queryClient.invalidateQueries({ queryKey: reimbKeys.cashAdvances() });
      void queryClient.invalidateQueries({ queryKey: reimbKeys.myWork() });
      void navigate(`/reimbursement/claims/${claim.id}`);
    },
    onError: (error) => {
      // A lost race: another tab (or the same user, twice) started one first.
      // Refetching turns this button into the link it should already have
      // been — a refusal with a path, not a dead end (§9.1 principle 4).
      if (
        error instanceof ApiError &&
        error.code === "reimb_liquidation_exists"
      ) {
        void queryClient.invalidateQueries({
          queryKey: reimbKeys.cashAdvances(),
        });
        toast("A liquidation for this advance already exists.");
        return;
      }
      toast("Could not start the liquidation. Please try again.");
    },
  });

  // A settled advance is a closed record — there is nothing left to liquidate.
  if (advance.status === "settled") return null;
  if (advance.liquidation_claim_id === null && !canStart) return null;

  if (advance.liquidation_claim_id !== null) {
    return (
      <Link
        to={`/reimbursement/claims/${advance.liquidation_claim_id}`}
        className="text-base text-link underline"
      >
        {advance.liquidation_ref_no
          ? `Open ${advance.liquidation_ref_no}`
          : "Open the liquidation"}
      </Link>
    );
  }

  return (
    <Button onClick={() => start.mutate()} loading={start.isPending}>
      Liquidate this advance
    </Button>
  );
}
