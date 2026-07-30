import { Link } from "react-router";
import { StatusChip, type SemanticStatus } from "../StatusChip/StatusChip";

export interface WorkItemRowProps {
  refNo: string | null;
  title: string;
  status: SemanticStatus;
  statusLabel: string;
  to: string;
  /** One muted meta line, composed by the page (holder · days · next action). */
  meta?: string;
}

/**
 * ui-standards §3.17 (R-2-wizard) — the My-Work inbox row: linked ref + title,
 * StatusChip right, one meta line. NOT the Pipeline-board card (that is a
 * board `<article>` with no link affordance).
 */
export function WorkItemRow({
  refNo,
  title,
  status,
  statusLabel,
  to,
  meta,
}: WorkItemRowProps) {
  return (
    <li className="flex min-h-11 flex-col gap-1 py-3">
      <div className="flex items-baseline justify-between gap-2">
        <Link to={to} className="text-base font-medium text-link underline">
          {refNo ? `${refNo} — ${title}` : title}
        </Link>
        <StatusChip status={status}>{statusLabel}</StatusChip>
      </div>
      {meta ? <p className="text-sm text-text-muted">{meta}</p> : null}
    </li>
  );
}
