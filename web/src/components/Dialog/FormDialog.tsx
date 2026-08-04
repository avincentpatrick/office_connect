import type { FormEvent, ReactNode } from "react";
import { Dialog as RadixDialog } from "radix-ui";
import { Button } from "../Button/Button";

export interface FormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  /** Plain-language framing of what submitting does. */
  description?: string;
  submitLabel: string;
  danger?: boolean;
  /** Disables the submit button and shows the spinner while in flight. */
  busy?: boolean;
  /** Called on form submit. The dialog does NOT close — the caller decides. */
  onSubmit: () => void;
  children: ReactNode;
}

/**
 * ui-standards §3.19 (R-4-screens) — dialog with a FORM body, for a decision
 * that needs input before it can be made (spec §9.4's return dialog).
 *
 * The one structural difference from ConfirmDialog, and the reason this exists
 * as a sibling rather than a prop on it: the submit button is NOT wrapped in
 * `RadixDialog.Close`, so a failed validation keeps the dialog open with the
 * user's work intact. ConfirmDialog's unconditional close is correct for a
 * yes/no confirm and wrong for anything you can get wrong. Closing on success
 * is the caller's job — it is the only party that knows the request landed.
 */
export function FormDialog({
  open,
  onOpenChange,
  title,
  description,
  submitLabel,
  danger = false,
  busy = false,
  onSubmit,
  children,
}: FormDialogProps) {
  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    onSubmit();
  };

  return (
    <RadixDialog.Root open={open} onOpenChange={onOpenChange}>
      <RadixDialog.Portal>
        <RadixDialog.Overlay className="fixed inset-0 z-40 bg-text/50" />
        <RadixDialog.Content className="fixed top-1/2 left-1/2 z-50 max-h-[90vh] w-full max-w-md -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-lg border border-border bg-bg p-6 shadow-md">
          <RadixDialog.Title className="text-lg font-bold text-text">
            {title}
          </RadixDialog.Title>
          {description ? (
            <RadixDialog.Description className="mt-2 text-base text-text-muted">
              {description}
            </RadixDialog.Description>
          ) : null}
          {/*
            `noValidate` turns OFF native constraint validation, deliberately.
            GOV.UK's form-structure guidance says to: the browser's own bubble
            appears in a language and wording we do not control, vanishes on
            blur, is not announced consistently, and — the reason it bit here —
            it BLOCKS the submit event entirely, so our validation never runs
            and the user never sees the message ui-standards §3.14 requires to
            match the server's. Our error text is the only error text.
          */}
          <form
            noValidate
            onSubmit={handleSubmit}
            className="mt-4 flex flex-col gap-4"
          >
            {children}
            <div className="flex justify-end gap-2">
              <RadixDialog.Close asChild>
                <Button variant="secondary">Cancel</Button>
              </RadixDialog.Close>
              <Button
                type="submit"
                variant={danger ? "danger" : "primary"}
                loading={busy}
              >
                {submitLabel}
              </Button>
            </div>
          </form>
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  );
}
