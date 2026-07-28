/**
 * Module-level toast bus so non-React code (e.g. the react-query QueryCache
 * error handler) can announce without a hook. ToastProvider subscribes.
 */

export type ToastVariant = "success" | "info";

export interface ToastMessage {
  id: number;
  message: string;
  variant: ToastVariant;
}

type Listener = (t: ToastMessage) => void;

export const toastListeners = new Set<Listener>();
let nextId = 1;

export function toast(message: string, variant: ToastVariant = "info"): void {
  const entry: ToastMessage = { id: nextId++, message, variant };
  for (const listener of toastListeners) listener(entry);
}
