import { useCallback, useEffect } from "react";
import { useBlocker } from "react-router";
import { ConfirmDialog } from "../../components/Dialog/Dialog";

/**
 * In-app + browser unsaved-changes guard for a wizard step. `shouldBlock` is
 * evaluated AT navigation time (pass a closure over the live form state and
 * any "we're leaving on purpose" ref) — save-and-return stays server-side;
 * this only catches walking away from typed-but-unsaved fields.
 */
export function UnsavedChangesGuard({ shouldBlock }: { shouldBlock: () => boolean }) {
  const blocker = useBlocker(useCallback(() => shouldBlock(), [shouldBlock]));

  useEffect(() => {
    const handler = (event: BeforeUnloadEvent) => {
      if (shouldBlock()) event.preventDefault();
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [shouldBlock]);

  if (blocker.state !== "blocked") return null;
  return (
    <ConfirmDialog
      open
      onOpenChange={(open) => {
        if (!open) blocker.reset();
      }}
      title="You have unsaved changes"
      consequence="If you leave this step now, the changes you typed will not be saved."
      confirmLabel="Leave without saving"
      danger
      onConfirm={() => blocker.proceed()}
    />
  );
}
