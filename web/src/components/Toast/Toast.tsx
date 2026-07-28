import { useEffect, useState, type ReactNode } from "react";
import { Toast as RadixToast } from "radix-ui";
import { Bell, CheckCircle2, Info } from "lucide-react";
import { cx } from "../../lib/cx";
import { toastListeners, type ToastMessage } from "./toast-bus";

/**
 * Toast / notification bell (ui-standards §3.13). Transient success/info via
 * toast() (./toast-bus); persistent items belong to the notification bell
 * (the bell's feed API is a recorded deferral — the badge is in-memory).
 */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastMessage[]>([]);

  useEffect(() => {
    const listener = (t: ToastMessage) => setItems((prev) => [...prev, t]);
    toastListeners.add(listener);
    return () => {
      toastListeners.delete(listener);
    };
  }, []);

  return (
    <RadixToast.Provider swipeDirection="right" duration={5000}>
      {children}
      {items.map((t) => (
        <RadixToast.Root
          key={t.id}
          onOpenChange={(open) => {
            if (!open) setItems((prev) => prev.filter((p) => p.id !== t.id));
          }}
          className="flex items-center gap-2 rounded-md border border-border bg-bg p-4 shadow-md"
        >
          {t.variant === "success" ? (
            <CheckCircle2 aria-hidden="true" className="size-5 text-status-done" />
          ) : (
            <Info aria-hidden="true" className="size-5 text-link" />
          )}
          <RadixToast.Description className="text-sm text-text">{t.message}</RadixToast.Description>
        </RadixToast.Root>
      ))}
      <RadixToast.Viewport className="fixed right-0 bottom-0 z-50 flex w-96 max-w-full flex-col gap-2 p-4" />
    </RadixToast.Provider>
  );
}

/** Top-bar notification bell — in-memory unread badge (feed API deferred). */
export function NotificationBell({ unread = 0 }: { unread?: number }) {
  return (
    <button
      type="button"
      className={cx(
        "relative inline-flex min-h-11 min-w-11 items-center justify-center rounded-md",
        "text-brand-contrast hover:bg-brand-contrast/10",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-contrast",
      )}
      aria-label={unread > 0 ? `Notifications (${unread} unread)` : "Notifications"}
    >
      <Bell aria-hidden="true" className="size-5" />
      {unread > 0 ? (
        <span
          aria-hidden="true"
          className="absolute top-1.5 right-1.5 min-w-4 rounded-lg bg-status-blocked px-1 text-center text-xs font-bold text-brand-contrast"
        >
          {unread}
        </span>
      ) : null}
    </button>
  );
}
