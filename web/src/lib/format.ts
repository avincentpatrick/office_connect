/**
 * Display formatting (ui-standards §5): dates as "Jul 20, 2026" in Manila,
 * money as "₱2,200.00". Money is DISPLAY ONLY — the server computes every
 * amount (core/money.py); the UI never does arithmetic on money.
 */

const MANILA_DATE = new Intl.DateTimeFormat("en-US", {
  timeZone: "Asia/Manila",
  month: "short",
  day: "numeric",
  year: "numeric",
});

const MANILA_DATETIME = new Intl.DateTimeFormat("en-US", {
  timeZone: "Asia/Manila",
  month: "short",
  day: "numeric",
  year: "numeric",
  hour: "numeric",
  minute: "2-digit",
});

const PESO = new Intl.NumberFormat("en-PH", {
  style: "currency",
  currency: "PHP",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export function formatManilaDate(value: string | Date): string {
  return MANILA_DATE.format(typeof value === "string" ? new Date(value) : value);
}

export function formatManilaDateTime(value: string | Date): string {
  return MANILA_DATETIME.format(typeof value === "string" ? new Date(value) : value);
}

/** Format a server-computed amount (2-dp string per the JSONB money convention). */
export function formatPeso(value: string | number): string {
  return PESO.format(typeof value === "string" ? Number(value) : value);
}
