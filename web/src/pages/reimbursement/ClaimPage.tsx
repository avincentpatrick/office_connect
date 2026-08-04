import { Navigate, useNavigate, useParams } from "react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "../../api/http";
import {
  reimbKeys,
  spawnReimbursement,
  type ClaimDetail,
} from "../../api/reimbursement";
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
import { CashAdvanceCard } from "./CashAdvanceCard";
import { PacketPreview } from "./PacketPreview";
import { SettlementOutcome } from "./SettlementDialog";
import { toast } from "../../components/Toast/toast-bus";
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

/** "LQ-2026-0001 — Liquidation" / "RB-2026-0007 — Travel claim". */
function claimTitle(claim: ClaimDetail): string {
  const noun = claim.kind === "liquidation" ? "Liquidation" : "Travel claim";
  return claim.ref_no ? `${claim.ref_no} — ${noun}` : noun;
}

/**
 * The settled liquidation's outcome, plus the traveller's one tap when the
 * advance did not cover the trip (spec §6.2).
 *
 * The button is gated on the SERVER's action set, never on a client-side
 * comparison of claimant ids — workflow-standards §3, "the UI never computes
 * permissions". `spawn` appears there only for the claimant, only on a settled
 * over-advance, and only while no live spawn exists; the service re-checks all
 * three, so neither layer is trusting the other.
 */
function SettlementOutcomePanel({ claim }: { claim: ClaimDetail }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const spawn = useMutation({
    mutationFn: () => spawnReimbursement(claim.id),
    onSuccess: (created) => {
      queryClient.setQueryData(reimbKeys.claim(created.id), created);
      void queryClient.invalidateQueries({ queryKey: reimbKeys.claim(claim.id) });
      void queryClient.invalidateQueries({ queryKey: reimbKeys.myWork() });
      toast("Draft claim started — finish it in the wizard.", "success");
      navigate(`/reimbursement/claims/${created.id}`);
    },
    onError: (error) => {
      toast(
        error instanceof ApiError
          ? error.message
          : "Something went wrong. Please try again.",
      );
      // A 409 means someone already claimed it (or this screen is stale) —
      // pull the truth back so the button re-renders honestly.
      if (error instanceof ApiError && error.status === 409) {
        void queryClient.invalidateQueries({
          queryKey: reimbKeys.claim(claim.id),
        });
      }
    },
  });

  return (
    <SettlementOutcome
      claim={claim}
      canSpawn={claim.available_actions.includes("spawn")}
      spawning={spawn.isPending}
      onSpawn={() => spawn.mutate()}
    />
  );
}

export function ClaimDetailView({ claim }: { claim: ClaimDetail }) {
  return (
    <DetailPage
      // The kind is in the TITLE, not a chip: a liquidation and a
      // reimbursement look identical on this page (same schema, same wizard,
      // same rail) but answer different questions to COA, and the one place a
      // reader always looks is the heading. The chip slot stays with STATUS —
      // spec §9.2's liquidation tracker is "the claim tracker + the countdown
      // ring", and both of those already ship.
      title={claimTitle(claim)}
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
        {/*
          Spec §6.2: the countdown shows on EVERY liquidation surface. When a
          claim is filed against an advance, the clock belongs beside it — an
          approver looking at the claim needs to see that the advance behind it
          is three days from COA interest.
        */}
        {claim.cash_advance ? (
          <CashAdvanceCard advance={claim.cash_advance} />
        ) : null}
        {/* How the money came out (R-6-liq-settle). Spec §6.3's derived-badge
            doctrine one level up: a settlement is a fact about the RECORD, not
            a status, so it renders beside the advance rather than as a chip. */}
        <SettlementOutcomePanel claim={claim} />
        <PacketPreview claim={claim} canPrepare={canPreparePacket(claim)} />
      </div>
    </DetailPage>
  );
}
