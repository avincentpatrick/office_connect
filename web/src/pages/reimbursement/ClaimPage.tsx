import { Navigate, useParams } from "react-router";
import { ApiError } from "../../api/http";
import type { ClaimDetail } from "../../api/reimbursement";
import { Card } from "../../components/Card/Card";
import { ErrorSummary } from "../../components/ErrorSummary/ErrorSummary";
import { PageSkeleton } from "../../components/Skeleton/Skeleton";
import { StatusChip } from "../../components/StatusChip/StatusChip";
import { SummaryList } from "../../components/SummaryList/SummaryList";
import { DetailPage } from "../../layouts/DetailPage";
import { formatManilaDate, formatPeso } from "../../lib/format";
import { NotFoundPage } from "../NotFoundPage";
import { ClaimActions } from "./ClaimActions";
import { ClaimTimeline } from "./ClaimTimeline";
import { PacketPreview } from "./PacketPreview";
import {
  CLAIM_STATUS_TO_SEMANTIC,
  SLA_STATE_LABEL,
  SLA_STATE_TO_SEMANTIC,
  canPreparePacket,
} from "./claim-status";
import { parseClaimId, useClaim } from "./use-claim";
import { firstIncompleteStep, stepPath } from "./wizard-steps";

/**
 * /reimbursement/claims/:claimId — the canonical claim URL, for everyone.
 *
 * A claim I can still edit resumes the wizard at the first incomplete step
 * (server-side save-and-return). Anything else renders the record, with the
 * tracker in the rail and — if the SERVER says I may act — the approval bar
 * (spec §9.2). One URL, three audiences, no client-side role routing: what
 * differs between a claimant, an approver and a bystander is entirely in
 * `available_actions`.
 */
export function ClaimPage() {
  const params = useParams();
  const id = parseClaimId(params.claimId);
  const query = useClaim(id);

  if (id === null) return <NotFoundPage />;
  if (query.isPending) return <PageSkeleton label="Loading the claim" />;
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
  // Resume the wizard only for someone who can actually move it forward. The
  // status alone would drag a REVIEWER opening a returned claim into a
  // stranger's wizard; the server's action set says whose ball it is.
  const canEdit =
    claim.available_actions.includes("submit") ||
    claim.available_actions.includes("resubmit");
  if (canEdit && (claim.status === "draft" || claim.status === "returned")) {
    return <Navigate to={stepPath(claim.id, firstIncompleteStep(claim))} replace />;
  }
  return <ClaimDetailView claim={claim} />;
}

export function ClaimDetailView({ claim }: { claim: ClaimDetail }) {
  return (
    <DetailPage
      title={claim.ref_no ? `${claim.ref_no} — Travel claim` : "Travel claim"}
      status={
        <StatusChip status={CLAIM_STATUS_TO_SEMANTIC[claim.status]}>
          {claim.status_label}
        </StatusChip>
      }
      actions={<ClaimActions claim={claim} />}
      rail={
        <>
          <Card title="Status">
            <dl className="flex flex-col gap-2 text-base text-text">
              {claim.holder_display ? (
                <div>
                  <dt className="text-sm text-text-muted">With</dt>
                  <dd>{claim.holder_display}</dd>
                </div>
              ) : null}
              {claim.next_action ? (
                <div>
                  <dt className="text-sm text-text-muted">Next action</dt>
                  <dd>{claim.next_action}</dd>
                </div>
              ) : null}
              {claim.sla_state && claim.sla_due_at ? (
                <div>
                  <dt className="text-sm text-text-muted">Due with this step</dt>
                  <dd className="flex items-center gap-2">
                    {formatManilaDate(claim.sla_due_at)}
                    <StatusChip status={SLA_STATE_TO_SEMANTIC[claim.sla_state]}>
                      {SLA_STATE_LABEL[claim.sla_state]}
                    </StatusChip>
                  </dd>
                </div>
              ) : null}
              {claim.totals ? (
                <div>
                  <dt className="text-sm text-text-muted">Grand total</dt>
                  <dd className="font-bold">{formatPeso(claim.totals.grand)}</dd>
                </div>
              ) : null}
              <div>
                <dt className="text-sm text-text-muted">Last updated</dt>
                <dd>{formatManilaDate(claim.updated_at)}</dd>
              </div>
            </dl>
          </Card>
          <ClaimTimeline claimId={claim.id} />
        </>
      }
    >
      <div className="flex flex-col gap-6">
        <section className="flex flex-col gap-2">
          <h2 className="text-lg font-bold text-text">Trip</h2>
          <SummaryList
            rows={[
              { key: "Claimant", value: claim.claimant.full_name },
              { key: "Purpose", value: claim.purpose },
              { key: "Destination", value: claim.destination },
              {
                key: "Travel dates",
                value:
                  claim.date_depart && claim.date_return
                    ? `${formatManilaDate(claim.date_depart)} to ${formatManilaDate(claim.date_return)}`
                    : null,
              },
              { key: "DPO number", value: claim.dpo_no },
            ]}
          />
        </section>
        <section className="flex flex-col gap-2">
          <h2 className="text-lg font-bold text-text">Itinerary</h2>
          <SummaryList
            rows={claim.legs.map((leg) => ({
              key: `Leg ${leg.seq}`,
              value: [
                leg.leg_date ? formatManilaDate(leg.leg_date) : null,
                leg.place,
                leg.transport_mode?.replace("_", " "),
                leg.fare ? formatPeso(leg.fare) : null,
              ]
                .filter(Boolean)
                .join(" · "),
            }))}
          />
        </section>
        {claim.totals ? (
          <section className="flex flex-col gap-2">
            <h2 className="text-lg font-bold text-text">Money</h2>
            <SummaryList
              rows={[
                { key: "Per diem", value: formatPeso(claim.totals.per_diem) },
                { key: "Transport", value: formatPeso(claim.totals.transport) },
                { key: "Other", value: formatPeso(claim.totals.other) },
                { key: "Grand total", value: formatPeso(claim.totals.grand) },
                { key: "To reimburse", value: formatPeso(claim.totals.to_reimburse) },
              ]}
            />
          </section>
        ) : null}
        {/* Spec §9.2's "packet PDF preview" — in the main column with the record
            it describes, not in the rail, and above the sticky decision bar so
            an approver reads the packet before the buttons come into reach. */}
        <PacketPreview claim={claim} canPrepare={canPreparePacket(claim)} />
      </div>
    </DetailPage>
  );
}
