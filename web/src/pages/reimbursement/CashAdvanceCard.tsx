import type { CashAdvance } from "../../api/reimbursement";
import { Callout } from "../../components/Callout/Callout";
import { CountdownRing } from "../../components/CountdownRing/CountdownRing";
import { StatusChip } from "../../components/StatusChip/StatusChip";
import type { SemanticStatus } from "../../components/StatusChip/StatusChip";
import { formatManilaDate, formatPeso } from "../../lib/format";

/**
 * One cash advance with its COA countdown (R-6-clock).
 *
 * A page-local COMPOSITION of inventory pieces (Card-style surface +
 * CountdownRing + StatusChip + Callout), the same call ui-standards made for
 * `GeneratedDocCard` and `PacketPreview`: §3 forbids a page using a component
 * outside the inventory, not composing inventory pieces on a page. The RING is
 * what got promoted to §3, because spec §6.2 puts the countdown "on every
 * liquidation surface" — three consumers on day one.
 *
 * Everything here is displayed, never derived: `days_remaining`,
 * `deadline_state` and the money all arrive computed (api-standards §2).
 */

/** Spec §5.4 status → the four platform semantics (ui-standards §2). */
const CA_STATUS_TO_SEMANTIC: Record<CashAdvance["status"], SemanticStatus> = {
  open: "waiting",
  liquidation_started: "waiting",
  settled: "done",
  overdue: "blocked",
};

export function CashAdvanceCard({
  advance,
  actions,
}: {
  advance: CashAdvance;
  actions?: React.ReactNode;
}) {
  return (
    <section
      className="flex flex-col gap-4 rounded-lg border border-border bg-bg p-4 shadow-sm"
      aria-label={
        advance.dv_no ? `Cash advance ${advance.dv_no}` : "Cash advance"
      }
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="text-sm text-text-muted">
            {advance.dv_no ?? "No DV number recorded"}
          </p>
          <p className="text-xl font-bold text-text">
            {formatPeso(advance.amount)}
          </p>
          <p className="text-sm text-text-muted">
            {advance.date_return
              ? `Returned to station ${formatManilaDate(advance.date_return)}`
              : "Return date not recorded yet"}
          </p>
        </div>
        {/*
          The chip reports the record's LIFECYCLE status; the ring below reports
          the CLOCK. Usually different facts — an advance can be "Open" and
          "Due soon" at once. When they coincide (an overdue advance is overdue
          on both counts) the chip is dropped, because the ring says everything
          it would plus how late and until when. R-5's rule, verbatim: a second
          chip must earn itself by reporting a second fact.
        */}
        {advance.status === "overdue" &&
        advance.deadline_state === "overdue" ? null : (
          <StatusChip status={CA_STATUS_TO_SEMANTIC[advance.status]}>
            {advance.status_label}
          </StatusChip>
        )}
      </div>

      {/*
        A SETTLED advance is not counting down to anything (R-6-liq-settle). The
        server already nulls the clock fields on one, so the ring would render
        its "not started" copy — which is worse than wrong here, because it says
        nothing has happened to an advance that is closed. It gets the closing
        date instead, which is the fact a reader actually wants.
      */}
      {advance.status === "settled" ? (
        // WHEN it closed, and nothing more. What the settlement actually was —
        // the receipt, the balance still owed — is the SettlementOutcome
        // callout's job, and saying it twice would be the "a second chip must
        // earn itself" rule broken in prose.
        <p className="text-sm text-text-muted">
          {advance.settled_at
            ? `Settled ${formatManilaDate(advance.settled_at)}`
            : "Settled"}
        </p>
      ) : (
        <CountdownRing
          daysRemaining={advance.days_remaining}
          state={advance.deadline_state}
          deadlineDate={advance.deadline_date}
          size="md"
        />
      )}

      {/*
        The COA consequence copy. The server sends it only once it applies
        (due-soon or past), so this renders a warning rather than boilerplate
        every advance carries from birth — §9.1 principle 4's "never block
        without a path", read as "never warn without a reason".
      */}
      {advance.overdue_note ? (
        <Callout
          status={advance.deadline_state === "overdue" ? "blocked" : "warn"}
          title="Liquidation deadline"
        >
          {advance.overdue_note}
        </Callout>
      ) : null}

      {actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}
    </section>
  );
}
