import type { ReactNode } from "react";

export interface BoardColumn {
  key: string;
  title: string;
  count?: number;
  children: ReactNode;
}

/** ui-standards §4.5 — Board page: pipeline columns of board cards; scrolls horizontally on phones. */
export function BoardPage({ title, columns }: { title: string; columns: BoardColumn[] }) {
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-bold text-text">{title}</h1>
      <div className="flex gap-4 overflow-x-auto pb-2">
        {columns.map((column) => (
          <section key={column.key} className="flex min-w-64 flex-1 flex-col gap-2">
            <h2 className="text-sm font-bold text-text-muted">
              {column.title}
              {column.count !== undefined ? ` (${column.count})` : null}
            </h2>
            <div className="flex flex-col gap-2 rounded-md bg-surface p-2">{column.children}</div>
          </section>
        ))}
      </div>
    </div>
  );
}
