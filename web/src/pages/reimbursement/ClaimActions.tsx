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
import { ChipGroup } from "../../components/ChipGroup/ChipGroup";
import { ConfirmDialog } from "../../components/Dialog/Dialog";
import { FormDialog } from "../../components/Dialog/FormDialog";
import { ErrorSummary } from "../../components/ErrorSummary/ErrorSummary";
import { TextareaField } from "../../components/TextareaField/TextareaField";
import { toast } from "../../components/Toast/toast-bus";
import { actionLabel, approveConsequence } from "./claim-status";
import { useReturnReasons } from "./use-claim";

/** Wording shared by the client-side guard and the server's 422 (ui-standards §14). */
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

  const canApprove = claim.available_actions.includes("approve");
  const canReturn = claim.available_actions.includes("return");

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

  // Below the hooks, never above them: the same component renders for a
  // claimant (nothing on offer) and an approver (two buttons), so bailing out
  // early would change the hook order between those two renders.
  if (!canApprove && !canReturn) return null;

  return (
    <div className="flex flex-col gap-3">
      {pageError ? <ErrorSummary errors={[{ message: pageError }]} /> : null}
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
            consequence={approveConsequence(claim.status)}
            confirmLabel={actionLabel("approve", claim.status)}
            onConfirm={() => approve.mutate()}
          />
        ) : null}
      </div>

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
