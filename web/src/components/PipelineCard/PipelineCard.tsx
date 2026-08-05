import { Link } from "react-router";
import { StatusChip, type SemanticStatus } from "../StatusChip/StatusChip";

export interface PipelineCardProps {
  /** Reference number, e.g. RB-2026-0001 (XX-YYYY-NNNN, never reused). */
  refNo: string;
  title: string;
  status: SemanticStatus;
  statusLabel: string;
  /** One compact meta line (owner, amount, age…). */
  meta?: string;
  /**
   * Where clicking the card goes. Optional — a card with no destination stays
   * the inert `<article>` it has always been.
   */
  to?: string;
}

/**
 * ui-standards §3.9 — compact card for kanban-style pipeline boards.
 *
 * **Inventory amendment (R-7-board):** the card gains an optional `to`. Spec
 * §9.6 says "clicking a card opens the tracker", and the inventory previously
 * said the card carried no link affordance at all — so the standard is amended
 * rather than quietly contradicted.
 *
 * The `<Link>` wraps the TITLE and a stretched overlay makes the whole card
 * clickable. Wrapping the entire card in one anchor would have worked too, and
 * would have given every card an accessible name of
 * "RB-2026-0001 Handed to FMS Iloilo field visit J. Dela Cruz · 12 working days
 * with FMS · ₱6,500.00" — one link, read aloud in full, forty times down a
 * column. The name is the title; the rest is context beside it.
 */
export function PipelineCard({
  refNo,
  title,
  status,
  statusLabel,
  meta,
  to,
}: PipelineCardProps) {
  return (
    <article className="relative flex flex-col gap-1 rounded-md border border-border bg-bg p-3 shadow-sm focus-within:outline focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-link">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium text-text-muted">{refNo}</span>
        <StatusChip status={status}>{statusLabel}</StatusChip>
      </div>
      {to ? (
        <p className="text-sm font-medium">
          <Link
            to={to}
            className="text-link underline after:absolute after:inset-0 after:content-[''] focus:outline-none"
          >
            {title}
          </Link>
        </p>
      ) : (
        <p className="text-sm font-medium text-text">{title}</p>
      )}
      {meta ? <p className="relative text-xs text-text-muted">{meta}</p> : null}
    </article>
  );
}
