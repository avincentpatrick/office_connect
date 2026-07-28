import { StatusChip, type SemanticStatus } from "../StatusChip/StatusChip";

export interface PipelineCardProps {
  /** Reference number, e.g. RB-2026-0001 (XX-YYYY-NNNN, never reused). */
  refNo: string;
  title: string;
  status: SemanticStatus;
  statusLabel: string;
  /** One compact meta line (owner, amount, age…). */
  meta?: string;
}

/** ui-standards §3.9 — compact card for kanban-style pipeline boards. */
export function PipelineCard({ refNo, title, status, statusLabel, meta }: PipelineCardProps) {
  return (
    <article className="flex flex-col gap-1 rounded-md border border-border bg-bg p-3 shadow-sm">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium text-text-muted">{refNo}</span>
        <StatusChip status={status}>{statusLabel}</StatusChip>
      </div>
      <p className="text-sm font-medium text-text">{title}</p>
      {meta ? <p className="text-xs text-text-muted">{meta}</p> : null}
    </article>
  );
}
