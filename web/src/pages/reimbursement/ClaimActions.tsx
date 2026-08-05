import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  approveClaim,
  reimbKeys,
  returnClaim,
  type ClaimDetail,
} from "../../api/reimbursement";
import { ApiError } from "../../api/http";
import { Button } from "../../components/Button/Button";
import { Callout } from "../../components/Callout/Callout";
import { ChipGroup } from "../../components/ChipGroup/ChipGroup";
import { ConfirmDialog } from "../../components/Dialog/Dialog";
import { FormDialog } from "../../components/Dialog/FormDialog";
import { ErrorSummary } from "../../components/ErrorSummary/ErrorSummary";
import { TextareaField } from "../../components/TextareaField/TextareaField";
import { toast } from "../../components/Toast/toast-bus";
import { EMPTY_CHECKLIST_SUMMARY } from "./checklist-status";
import { actionLabel, approveConsequence } from "./claim-status";
import { FmsStatusDialog } from "./FmsStatusDialog";
import { MarkPaidDialog } from "./MarkPaidDialog";
import { SettlementDialog } from "./SettlementDialog";
import { useReturnReasons } from "./use-claim";

/** Wording shared by the client-side guard and the server's 422 (ui-standards §3.14). */
const NO_REASON_MESSAGE = "Select at least one reason for returning this claim.";
const NO_COMMENT_MESSAGE =
  "Explain what needs fixing — the claimant sees this comment.";

/**
 * The approver's decision bar (spec §9.2) — rendered from the SERVER's action
 * set and nothing else (workflow-standards §3). If `available_actions` is
 * empty this renders nothing at all, which is exactly what a claimant, a
 * bystander, and an approver who already acted should see.
 */
export function ClaimActions({ claim }: { claim: ClaimDetail }) {
  const queryClient = useQueryClient();
  const [returnOpen, setReturnOpen] = useState(false);
  const [reasonIds, setReasonIds] = useState<string[]>([]);
  const [comment, setComment] = useState("");
  const [reasonError, setReasonError] = useState<string>();
  const [commentError, setCommentError] = useState<string>();
  const [pageError, setPageError] = useState<string>();
  const reasons = useReturnReasons();

  const [settleOpen, setSettleOpen] = useState(false);
  const [payOpen, setPayOpen] = useState(false);
  const [fmsOpen, setFmsOpen] = useState(false);
  const canApprove = claim.available_actions.includes("approve");
  const canReturn = claim.available_actions.includes("return");
  // The two terminal gates. The server REWROTE `approve` into `settle` (a
  // liquidation) or `mark_paid` (a reimbursement) here, so this is the same
  // authorization it always was — the act just has to carry the facts now, and
  // each lives on its own route.
  const canSettle = claim.available_actions.includes("settle");
  const canMarkPaid = claim.available_actions.includes("mark_paid");
  // Not a transition: relaying appends to the FMS journey and moves nothing.
  // It rides the action set so the browser never infers who may do it.
  const canRelay = claim.available_actions.includes("relay_fms");

  const onSettled = (updated: ClaimDetail) => {
    // The mutation returns the whole claim, so the detail view, the action set
    // and the CAS token all refresh together — no refetch race.
    queryClient.setQueryData(reimbKeys.claim(claim.id), updated);
    void queryClient.invalidateQueries({ queryKey: reimbKeys.myWork() });
    void queryClient.invalidateQueries({
      queryKey: reimbKeys.timeline(claim.id),
    });
  };

  const onError = (error: unknown) => {
    setPageError(
      error instanceof ApiError
        ? error.message
        : "Something went wrong. Please try again.",
    );
    // A 409 means the claim moved under us (someone else acted, or the screen
    // is stale) — pull the truth back so the buttons re-render honestly.
    if (error instanceof ApiError && error.status === 409) {
      void queryClient.invalidateQueries({
        queryKey: reimbKeys.claim(claim.id),
      });
    }
  };

  const approve = useMutation({
    mutationFn: () =>
      approveClaim(claim.id, { expected_version: claim.row_version }),
    onSuccess: (updated) => {
      setPageError(undefined);
      onSettled(updated);
      toast(`${claim.ref_no ?? "The claim"} approved.`, "success");
    },
    onError,
  });

  const sendBack = useMutation({
    mutationFn: () =>
      returnClaim(claim.id, {
        comment,
        reason_ids: reasonIds.map(Number),
        expected_version: claim.row_version,
      }),
    onSuccess: (updated) => {
      setPageError(undefined);
      setReturnOpen(false);
      setReasonIds([]);
      setComment("");
      onSettled(updated);
      toast(`${claim.ref_no ?? "The claim"} returned to the claimant.`, "success");
    },
    onError: (error) => {
      // Keep the dialog OPEN with the approver's work intact — that is the
      // whole reason this uses FormDialog rather than ConfirmDialog.
      onError(error);
    },
  });

  const submitReturn = () => {
    const noReasons = reasonIds.length === 0;
    const noComment = comment.trim().length === 0;
    setReasonError(noReasons ? NO_REASON_MESSAGE : undefined);
    setCommentError(noComment ? NO_COMMENT_MESSAGE : undefined);
    if (noReasons || noComment) return;
    sendBack.mutate();
  };

  const checklist = claim.checklist ?? EMPTY_CHECKLIST_SUMMARY;
  const flags = checklist.flags;
  const blocking = checklist.blocking;

  // Below the hooks, never above them: the same component renders for a
  // claimant (nothing on offer) and an approver (two buttons), so bailing out
  // early would change the hook order between those two renders.
  //
  // The callouts must SURVIVE the "no actions on offer" case, because that is
  // exactly when an approver most needs to know why: the server withholds
  // `approve` when a required document is missing, and a vanished button with
  // no explanation is the §9.1-principle-4 failure this whole increment exists
  // to prevent. Bail out only when there is nothing at all to say.
  if (
    !canApprove &&
    !canReturn &&
    !canSettle &&
    !canMarkPaid &&
    !canRelay &&
    flags.length === 0 &&
    blocking.length === 0
  ) {
    return null;
  }

  return (
    <div className="flex flex-col gap-3">
      {pageError ? <ErrorSummary errors={[{ message: pageError }]} /> : null}

      {/* Red before amber: a hard stop outranks a warning. */}
      {blocking.length > 0 ? (
        <Callout status="blocked" title="Required documents are missing">
          <p>This claim cannot be approved until the claimant attaches them.</p>
          <ul className="mt-1 flex list-disc flex-col gap-1 pl-5">
            {blocking.map((item) => (
              <li key={item.catalog_id}>{item.label}</li>
            ))}
          </ul>
        </Callout>
      ) : null}

      {/* Spec §9.4 — flagged auto-checks render as amber callouts above the
          buttons. A flag NEVER disables approving; it informs the decision. */}
      {flags.length > 0 ? (
        <Callout
          status="warn"
          title={
            flags.length === 1
              ? "1 automatic check flagged"
              : `${flags.length} automatic checks flagged`
          }
        >
          <p>
            You can still approve. Approving past a flag is recorded against
            your name.
          </p>
          <ul className="mt-1 flex list-disc flex-col gap-1 pl-5">
            {flags.map((flag) => (
              <li key={`${flag.catalog_id}-${flag.check_type}`}>
                <span className="font-medium">{flag.label}</span> — {flag.message}
              </li>
            ))}
          </ul>
        </Callout>
      ) : null}

      {/* Exactly one primary per screen-moment (ui-standards §3.1): approving
          is the expected path, returning is the exception. */}
      <div className="flex gap-2">
        {canReturn ? (
          <Button
            variant="secondary"
            className="flex-1"
            onClick={() => setReturnOpen(true)}
          >
            {actionLabel("return", claim.status)}
          </Button>
        ) : null}
        {canApprove ? (
          <ConfirmDialog
            trigger={
              <Button variant="primary" className="flex-1" loading={approve.isPending}>
                {actionLabel("approve", claim.status)}
              </Button>
            }
            title={actionLabel("approve", claim.status)}
            consequence={approveConsequence(claim.status, flags.length)}
            confirmLabel={actionLabel("approve", claim.status)}
            onConfirm={() => approve.mutate()}
          />
        ) : null}
        {/* Settling carries data, so it opens a FORM rather than a confirm —
            the consequence is stated in the dialog's own description, which
            varies with the branch the money took. */}
        {canSettle ? (
          <Button
            variant="primary"
            className="flex-1"
            onClick={() => setSettleOpen(true)}
          >
            {actionLabel("settle", claim.status)}
          </Button>
        ) : null}
        {/* Same shape one chain over: closing a claim records a payment
            reference, so it opens a FORM and states its consequence there. */}
        {canMarkPaid ? (
          <Button
            variant="primary"
            className="flex-1"
            onClick={() => setPayOpen(true)}
          >
            {actionLabel("mark_paid", claim.status)}
          </Button>
        ) : null}
      </div>

      {/* Relaying is not a decision, so it sits BELOW the decision row and
          never takes the primary slot (ui-standards §3.1: one primary per
          screen-moment). While a claim is with FMS it is usually the only thing
          on offer — the packet is out of the bureau's hands, and saying where
          it got to is the only honest act left. */}
      {canRelay ? (
        <div>
          <Button variant="secondary" onClick={() => setFmsOpen(true)}>
            {actionLabel("relay_fms", claim.status)}
          </Button>
        </div>
      ) : null}

      {canSettle ? (
        <SettlementDialog
          claim={claim}
          open={settleOpen}
          onOpenChange={setSettleOpen}
        />
      ) : null}

      {canMarkPaid ? (
        <MarkPaidDialog
          claim={claim}
          open={payOpen}
          onOpenChange={setPayOpen}
        />
      ) : null}

      {canRelay ? (
        <FmsStatusDialog
          claim={claim}
          open={fmsOpen}
          onOpenChange={setFmsOpen}
        />
      ) : null}

      <FormDialog
        open={returnOpen}
        onOpenChange={(open) => {
          setReturnOpen(open);
          if (!open) {
            setReasonError(undefined);
            setCommentError(undefined);
          }
        }}
        title="Return this claim"
        description="The claim goes back to the claimant to fix and resubmit. They see your reasons and comment."
        submitLabel="Return claim"
        danger
        busy={sendBack.isPending}
        onSubmit={submitReturn}
      >
        <ChipGroup
          id="return-reasons"
          legend="Why are you returning it?"
          help="Pick every reason that applies."
          error={reasonError}
          options={(reasons.data ?? []).map((reason) => ({
            value: String(reason.id),
            label: reason.label,
          }))}
          value={reasonIds}
          onChange={(next) => {
            setReasonIds(next);
            if (next.length > 0) setReasonError(undefined);
          }}
        />
        <TextareaField
          id="return-comment"
          label="What needs fixing?"
          help="The claimant sees this word for word."
          error={commentError}
          value={comment}
          onChange={(event) => {
            setComment(event.target.value);
            if (event.target.value.trim()) setCommentError(undefined);
          }}
        />
      </FormDialog>
    </div>
  );
}
