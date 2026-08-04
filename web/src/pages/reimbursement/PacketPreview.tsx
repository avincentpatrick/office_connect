import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "../../api/http";
import {
  generateClaimDocuments,
  reimbKeys,
  type ClaimDetail,
} from "../../api/reimbursement";
import { Button } from "../../components/Button/Button";
import { Callout } from "../../components/Callout/Callout";
import { Card } from "../../components/Card/Card";
import { StatusChip } from "../../components/StatusChip/StatusChip";
import { formatManilaDate } from "../../lib/format";

export interface PacketPreviewProps {
  claim: ClaimDetail;
  /**
   * Whether to offer "Prepare the packet" when none exists. The server owns the
   * real rule (owner-while-editable, or a scoped reviewer); this only decides
   * whether to show a button that would otherwise 403 for a bystander.
   */
  canPrepare?: boolean;
}

/**
 * Spec §9.2 — the approval screen's "packet PDF preview".
 *
 * A page-local COMPOSITION of inventory pieces (Card, StatusChip, Button,
 * Callout plus a frame), not a new inventory component — the same call
 * `GeneratedDocCard` made at R-5-gen, for the same reason: one consumer is not
 * yet a pattern. Promote to ui-standards §3 when a second module needs an
 * embedded document preview.
 *
 * **Why the frame is `lg`-only.** iOS Safari does not render a PDF inside an
 * iframe — it shows a blank box or a download stub. §9.2 marks the approval
 * screen phone-first, so an embedded-always frame would fail on precisely the
 * device the spec cares most about. The link is therefore the primary
 * affordance at every width and the frame is the desktop enhancement over it.
 * Only the frame is breakpoint-hidden, so no node is rendered twice and
 * `DetailPage`'s single-node rule holds.
 *
 * The frame can render at all only because the server serves a generated PDF
 * with `Content-Disposition: inline` (api-standards §9c) and sets no
 * frame-blocking header for its own origin. An uploaded PDF is never served
 * that way, which is exactly the point.
 */
export function PacketPreview({ claim, canPrepare = false }: PacketPreviewProps) {
  const queryClient = useQueryClient();
  const [notice, setNotice] = useState<string | undefined>();
  const [error, setError] = useState<string | undefined>();

  const packet = claim.packet ?? null;

  const prepare = useMutation({
    mutationFn: () => generateClaimDocuments(claim.id),
    onMutate: () => setError(undefined),
    onSuccess: (response) => {
      setNotice(
        response.queued
          ? "We are preparing the packet. It appears here in a moment."
          : // §19.12: never a 500, never a blocked decision — an honest notice.
            // The approve and return buttons stay live either way.
            "Document preparation is unavailable right now. The claim is unaffected and you can still decide on it; the packet is prepared when the service is back.",
      );
      // The worker writes the snapshot this request cannot see. One delayed
      // refetch of the claim (which carries `packet`) beats a polling loop that
      // would keep running long after the user has left the page.
      window.setTimeout(() => {
        void queryClient.invalidateQueries({ queryKey: reimbKeys.claim(claim.id) });
      }, 2500);
    },
    onError: (err) => {
      setNotice(undefined);
      setError(
        // The server's sentence verbatim (ui-standards §3.14) — it names the
        // actual reason, e.g. that the Money step is not finished.
        err instanceof ApiError
          ? err.message
          : "Something went wrong. Please try again.",
      );
    },
  });

  const title = "Packet";

  if (!packet) {
    return (
      <Card
        title={title}
        actions={
          canPrepare ? (
            <Button
              variant="secondary"
              loading={prepare.isPending}
              onClick={() => prepare.mutate()}
            >
              Prepare the packet
            </Button>
          ) : undefined
        }
      >
        <div className="flex flex-col gap-3">
          {error ? (
            <Callout status="blocked" title="We could not prepare the packet">
              {error}
            </Callout>
          ) : null}
          {notice ? (
            <Callout status="waiting" title="Preparing the packet" live="polite">
              {notice}
            </Callout>
          ) : null}
          <p className="text-base text-text-muted">
            The printable packet has not been prepared yet. It is built
            automatically when the claim is submitted.
          </p>
        </div>
      </Card>
    );
  }

  return (
    <Card
      title={title}
      status={
        // Draft-ness is a fact about the PDF, not about the claim: the file
        // carries a DRAFT watermark and no reference number, and someone about
        // to print it needs to know that before they walk it to Accounting.
        packet.is_draft ? (
          <StatusChip status="warn">Draft copy</StatusChip>
        ) : (
          <StatusChip status="done">Filed copy</StatusChip>
        )
      }
    >
      <div className="flex flex-col gap-3">
        <p className="text-sm text-text-muted">
          Prepared {formatManilaDate(packet.generated_at)}
          {packet.is_draft
            ? " — this copy has no reference number and is not the filed document."
            : null}
        </p>
        <p>
          <a
            href={packet.download_path}
            target="_blank"
            rel="noopener noreferrer"
            className="text-base text-link underline"
          >
            Open the packet
            {/* An unannounced context switch is a WCAG 3.2.5 failure. */}
            <span className="sr-only"> (opens in a new tab)</span>
          </a>
        </p>
        {/* `title` is required: an untitled frame is announced as "frame" and
            nothing else. Below `lg` the link above is the whole affordance. */}
        <iframe
          title="Claim packet preview"
          src={packet.download_path}
          className="hidden h-[70vh] w-full rounded-md border border-border lg:block"
        />
      </div>
    </Card>
  );
}
