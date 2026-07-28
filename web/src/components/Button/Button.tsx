import type { ButtonHTMLAttributes } from "react";
import { Loader2 } from "lucide-react";
import { cx } from "../../lib/cx";

type Variant = "primary" | "secondary" | "danger";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  loading?: boolean;
}

const VARIANT_CLASSES: Record<Variant, string> = {
  primary: "bg-brand text-brand-contrast hover:opacity-90",
  secondary: "border border-border bg-surface text-text hover:bg-bg",
  danger: "bg-status-blocked text-brand-contrast hover:opacity-90",
};

/**
 * ui-standards §3.1 — exactly one primary Button per screen-moment (enforced
 * by review, not code). Loading keeps the label visible and blocks re-submit.
 */
export function Button({
  variant = "primary",
  loading = false,
  disabled,
  className,
  children,
  type = "button",
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cx(
        "inline-flex min-h-11 items-center justify-center gap-2 rounded-md px-4 text-base font-medium",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand",
        "disabled:cursor-not-allowed disabled:opacity-50",
        VARIANT_CLASSES[variant],
        className,
      )}
      {...rest}
    >
      {loading ? <Loader2 aria-hidden="true" className="size-4 animate-spin" /> : null}
      {children}
    </button>
  );
}
