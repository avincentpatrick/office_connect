import type { ReactNode } from "react";
import { Navigate, useParams } from "react-router";
import { ApiError } from "../../api/http";
import type { ClaimDetail } from "../../api/reimbursement";
import { ErrorSummary } from "../../components/ErrorSummary/ErrorSummary";
import { PageSkeleton } from "../../components/Skeleton/Skeleton";
import { NotFoundPage } from "../NotFoundPage";
import { ClaimDetailView } from "./ClaimPage";
import { parseClaimId, useClaim } from "./use-claim";
import { stepPath, type StepSlug } from "./wizard-steps";

/**
 * The wizard's route guard (routing plumbing, like app/guards.tsx): loads the
 * claim, 404s bad/foreign/missing ids alike (no existence leak — same choice
 * as the flag gate), and keeps step routes editable-only: a non-editable claim
 * renders its read-only detail IN PLACE (never a <Navigate> — the post-submit
 * cache write would race the page's own navigation to /confirmation, since
 * react-router navigations are async). /confirmation with a still-draft claim
 * bounces back to review.
 */
export function ClaimStepGuard({
  slug,
  children,
}: {
  slug: StepSlug | "confirmation";
  children: (claim: ClaimDetail) => ReactNode;
}) {
  const params = useParams();
  const id = parseClaimId(params.claimId);
  const query = useClaim(id);

  if (id === null) return <NotFoundPage />;
  if (query.isPending) return <PageSkeleton label="Loading your claim" />;
  if (query.isError) {
    const error = query.error;
    if (error instanceof ApiError && (error.status === 404 || error.status === 403)) {
      return <NotFoundPage />;
    }
    return (
      <ErrorSummary
        errors={[
          {
            message:
              error instanceof ApiError
                ? error.message
                : "Something went wrong. Please try again.",
          },
        ]}
      />
    );
  }

  const claim = query.data;
  const editable = claim.status === "draft" || claim.status === "returned";
  if (slug === "confirmation") {
    // "Claim submitted" is only true for claims actually in the workflow:
    // claimant-held claims bounce to review, cancelled ones show the record.
    if (editable) {
      return <Navigate to={stepPath(claim.id, "review")} replace />;
    }
    if (claim.status === "cancelled") {
      return <ClaimDetailView claim={claim} />;
    }
  } else if (!editable) {
    return <ClaimDetailView claim={claim} />;
  }
  return <>{children(claim)}</>;
}
