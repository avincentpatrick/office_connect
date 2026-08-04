import { formatManilaDate } from "../../lib/format";
import type { ChecklistItem } from "../../api/reimbursement";

export interface GeneratedDocCardProps {
  item: ChecklistItem;
  /** True while a generation request is in flight for this claim. */
  busy?: boolean;
}

/**
 * Spec §9.3 step 4: "generated docs show as `Generated ✓` cards with preview".
 *
 * A page-local COMPOSITION of inventory pieces (StatusChip plus a link), not a
 * new inventory component. ui-standards §3 forbids a page using a component
 * outside the inventory; it does not forbid composing inventory pieces on a
 * page, which is what the file list beside this one already does. Promote it to
 * §3 when a second module needs it — the same discipline that kept the
 * checklist engine's storage module-side at R-3.
 *
 * **Why the preview is a link and not an embedded frame.** The Documents step is
 * a task list, and three inline PDF viewers stacked in it would be unusable on
 * the phone this module is designed for. The link opens the document in a new
 * tab, where the browser's own viewer is better than anything embedded here.
 * The single embedded packet preview the approver gets (spec §9.2) is a
 * different surface and lands with the printable packet.
 *
 * The link works at all only because the server serves generated PDFs with
 * `Content-Disposition: inline` — uploaded files stay `attachment` and would
 * download instead. That decision is made from the row's provenance, server-
 * side; the client never asks for it.
 */
export function GeneratedDocCard({ item, busy = false }: GeneratedDocCardProps) {
  // The most recent generated file for this item. The server supersedes rather
  // than deletes, but only the live join rows come back, so this is normally a
  // single element; taking the last is defensive, not speculative.
  const file = [...item.files].reverse().find((f) => f.origin === "generated");

  if (!file) {
    return (
      <p className="text-sm text-text-muted">
        {busy
          ? "Preparing this document…"
          : "This will be prepared for you. You can submit without it."}
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-2 rounded-md border border-border bg-surface px-3 py-3">
      {/* NO status chip here. The task-list row already carries "Generated", and
          unlike an upload there is no second fact to report: a generated file is
          born scan-clean, so the item's state and the file's state are the same
          state. R-3's two-chip rule exists because an upload's item and file
          genuinely disagree; repeating one fact twice would be noise, not
          honesty. */}
      <span className="text-sm text-text-muted">
        Prepared {formatManilaDate(file.uploaded_at)}
      </span>
      {file.download_path ? (
        <a
          href={file.download_path}
          target="_blank"
          rel="noopener noreferrer"
          className="text-base text-link underline"
        >
          Preview {item.label}
          {/* The new tab is announced, not just implied by the icon-free link —
              an unannounced context switch is a WCAG 3.2.5 failure. */}
          <span className="sr-only"> (opens in a new tab)</span>
        </a>
      ) : (
        <span className="text-base text-text">{file.filename}</span>
      )}
    </div>
  );
}
