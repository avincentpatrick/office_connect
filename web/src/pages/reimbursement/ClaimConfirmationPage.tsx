import { Link } from "react-router";
import { Card } from "../../components/Card/Card";
import { ConfirmationPanel } from "../../components/ConfirmationPanel/ConfirmationPanel";
import { ClaimStepGuard } from "./ClaimStepGuard";

/**
 * Post-submit confirmation — a plain content page inside the App shell
 * (ui-standards §4 R-2-wizard note): the transaction is complete, so no
 * stepper or task list. Reached with `replace: true` so Back never re-offers
 * submit.
 */
export function ClaimConfirmationPage() {
  return (
    <ClaimStepGuard slug="confirmation">
      {(claim) => (
        <div className="mx-auto flex w-full max-w-xl flex-col gap-6">
          <ConfirmationPanel
            title="Claim submitted"
            referenceLabel="Your reference number"
            reference={claim.ref_no ?? "—"}
          >
            <p>Keep this reference — it appears on every update about your claim.</p>
          </ConfirmationPanel>
          <Card title="What happens next">
            <p className="text-base text-text">
              Your claim is now with {claim.holder_display ?? "the approver"} (
              {claim.status_label}).
              {claim.next_action ? ` Their next action: ${claim.next_action.toLowerCase()}.` : ""}
            </p>
            <p className="mt-2 text-base text-text">
              You can track it from My Work — it appears under “Your claims in
              flight” with the holder and next action.
            </p>
          </Card>
          <div className="flex flex-wrap gap-4">
            <Link
              to={`/reimbursement/claims/${claim.id}`}
              className="text-base text-link underline"
            >
              Track this claim
            </Link>
            <Link to="/reimbursement" className="text-base text-link underline">
              Go to My Work
            </Link>
          </div>
        </div>
      )}
    </ClaimStepGuard>
  );
}
