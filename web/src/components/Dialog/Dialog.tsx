import type { ReactNode } from "react";
import { Dialog as RadixDialog } from "radix-ui";
import { Button } from "../Button/Button";

export interface ConfirmDialogProps {
  /** The element that opens the dialog (rendered via asChild). */
  trigger: ReactNode;
  title: string;
  /** Plain-language statement of the consequence (§3.10 — required for destructive confirms). */
  consequence: string;
  confirmLabel: string;
  danger?: boolean;
  onConfirm: () => void;
}

/**
 * ui-standards §3.10 — dialog / confirm sheet (Radix: focus trap, escape,
 * portal, aria wiring). Destructive confirms state consequences plainly.
 */
export function ConfirmDialog({
  trigger,
  title,
  consequence,
  confirmLabel,
  danger = false,
  onConfirm,
}: ConfirmDialogProps) {
  return (
    <RadixDialog.Root>
      <RadixDialog.Trigger asChild>{trigger}</RadixDialog.Trigger>
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
