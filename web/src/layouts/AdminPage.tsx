import type { ReactNode } from "react";
import { Card } from "../components/Card/Card";

/** ui-standards §4.6 — Admin / settings page: sectioned forms with per-section save. */
export function AdminPage({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-bold text-text">{title}</h1>
      {children}
    </div>
  );
}

export interface AdminSectionProps {
  title: string;
  description?: string;
  /** Per-section save / action row. */
  actions?: ReactNode;
  children: ReactNode;
}

export function AdminSection({ title, description, actions, children }: AdminSectionProps) {
  return (
    <Card title={title} actions={actions}>
      {description ? <p className="mb-4 text-sm text-text-muted">{description}</p> : null}
      {children}
    </Card>
  );
}
