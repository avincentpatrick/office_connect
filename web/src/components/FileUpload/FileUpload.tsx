import { useRef, useState, type ChangeEvent, type DragEvent } from "react";
import { Loader2, UploadCloud } from "lucide-react";
import { cx } from "../../lib/cx";

export interface FileUploadProps {
  /** DOM id — also the label's htmlFor and the aria-describedby stem. */
  id: string;
  /** The plain-language instruction. This IS the accessible name. */
  label: string;
  help?: string;
  /** Validation message — states what to do next, never just "invalid". */
  error?: string;
  /** Forwarded verbatim, e.g. "image/*,application/pdf". */
  accept?: string;
  /**
   * Phone camera capture. WARNING: on iOS/Android this FORCES the camera and
   * removes the gallery/files option. Leave unset unless camera-only is the
   * intent — `accept="image/*,…"` alone already puts Camera in the OS sheet.
   */
  capture?: "user" | "environment";
  multiple?: boolean;
  /** Upload in flight: blocks a second pick and sets aria-busy. */
  busy?: boolean;
  disabled?: boolean;
  /** Polite live-region text, e.g. "Boarding pass.jpg attached." */
  status?: string;
  /** Extra ids to chain into aria-describedby (e.g. a scan note). */
  describedBy?: string;
  onFiles: (files: File[]) => void;
}

/**
 * ui-standards §3.21 (R-3) — file upload for the claim's documentary packet.
 *
 * A real, focusable `<input type="file">` styled through `peer-*` (the same
 * idiom §8 documents for ChipGroup), with the drop zone as its `<label>`.
 * Drag-and-drop is a mouse-only enhancement layered over that one control —
 * there is no drop-only affordance, so keyboard users are never second-class
 * and no custom key handling or focus restoration is needed.
 *
 * No upload percentage: `fetch` exposes no upload progress, and forking the one
 * API wrapper onto XMLHttpRequest to draw a bar is not worth it. The spinner
 * plus the live region is the honest state.
 */
export function FileUpload({
  id,
  label,
  help,
  error,
  accept,
  capture,
  multiple = false,
  busy = false,
  disabled = false,
  status,
  describedBy,
  onFiles,
}: FileUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const helpId = help ? `${id}-help` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const described =
    [helpId, errorId, describedBy].filter(Boolean).join(" ") || undefined;

  const emit = (files: FileList | null) => {
    const list = Array.from(files ?? []);
    if (list.length > 0) onFiles(list);
    // Reset so re-picking the SAME file fires `change` again — otherwise a
    // retry after a rejected upload silently does nothing.
    if (inputRef.current) inputRef.current.value = "";
  };

  const handleChange = (event: ChangeEvent<HTMLInputElement>) =>
    emit(event.target.files);

  const handleDrop = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    setDragging(false);
    if (disabled || busy) return;
    emit(event.dataTransfer.files);
  };

  return (
    <div className="flex flex-col gap-1">
      {help ? (
        <p id={helpId} className="text-sm text-text-muted">
          {help}
        </p>
      ) : null}
      {/* Input FIRST — Tailwind's `peer-*` is a following-sibling selector.
          sr-only but focusable: Tab lands here and Enter/Space opens the
          native picker. */}
      <input
        ref={inputRef}
        type="file"
        id={id}
        className="peer sr-only"
        accept={accept}
        capture={capture}
        multiple={multiple}
        disabled={disabled || busy}
        aria-describedby={described}
        aria-invalid={error ? true : undefined}
        aria-busy={busy || undefined}
        onChange={handleChange}
      />
      <label
        htmlFor={id}
        onDragOver={(event) => {
          event.preventDefault();
          if (!disabled && !busy) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        className={cx(
          "flex min-h-11 cursor-pointer flex-col items-center justify-center gap-1",
          "rounded-md border-2 border-dashed p-4 text-center text-base text-text",
          dragging
            ? "border-brand bg-surface"
            : error
              ? "border-status-blocked"
              : "border-border",
          "peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-brand",
          "peer-disabled:cursor-not-allowed peer-disabled:opacity-50",
        )}
      >
        {busy ? (
          <Loader2
            aria-hidden="true"
            className="size-6 animate-spin text-text-muted"
          />
        ) : (
          <UploadCloud aria-hidden="true" className="size-6 text-text-muted" />
        )}
        <span className="font-medium">{label}</span>
        <span className="text-sm text-text-muted">
          Choose a file, or drop one here
        </span>
      </label>
      {/* Present from mount so only CHANGES are announced. */}
      <p aria-live="polite" className="text-sm text-text-muted">
        {status}
      </p>
      {error ? (
        <p id={errorId} className="text-sm font-medium text-status-blocked">
          {error}
        </p>
      ) : null}
    </div>
  );
}
