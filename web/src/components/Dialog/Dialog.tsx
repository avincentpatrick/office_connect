import type { ReactNode } from "react";
import { Dialog as RadixDialog } from "radix-ui";
import { Button } from "../Button/Button";

export interface ConfirmDialogProps {
  /** The element that opens the dialog (omit in controlled mode). */
  trigger?: ReactNode;
  title: string;
  /** Plain-language statement of the consequence (§3.10 — required for destructive confirms). */
  consequence: string;
  confirmLabel: string;
  danger?: boolean;
  onConfirm: () => void;
  /** Controlled mode (R-2-wizard) — for router-driven prompts with no trigger element. */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

/**
 * ui-standards §3.10 — dialog / confirm sheet (Radix: focus trap, escape,
 * portal, aria wiring). Destructive confirms state consequences plainly.
 * Pass `open`/`onOpenChange` (and omit `trigger`) to drive it externally,
 * e.g. from a router navigation blocker.
 */
export function ConfirmDialog({
  trigger,
  title,
  consequence,
  confirmLabel,
  danger = false,
  onConfirm,
  open,
  onOpenChange,
}: ConfirmDialogProps) {
  return (
    <RadixDialog.Root open={open} onOpenChange={onOpenChange}>
      {trigger ? <RadixDialog.Trigger asChild>{trigger}</RadixDialog.Trigger> : null}
      <RadixDialog.Portal>
        <RadixDialog.Overlay className="fixed inset-0 z-40 bg-text/50" />
        <RadixDialog.Content className="fixed top-1/2 left-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg border border-border bg-bg p-6 shadow-md">
          <RadixDialog.Title className="text-lg font-bold text-text">{title}</RadixDialog.Title>
          <RadixDialog.Description className="mt-2 text-base text-text">
            {consequence}
          </RadixDialog.Description>
          <div className="mt-6 flex justify-end gap-2">
            <RadixDialog.Close asChild>
              <Button variant="secondary">Cancel</Button>
            </RadixDialog.Close>
            <RadixDialog.Close asChild>
              <Button variant={danger ? "danger" : "primary"} onClick={onConfirm}>
                {confirmLabel}
              </Button>
            </RadixDialog.Close>
          </div>
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  );
}
