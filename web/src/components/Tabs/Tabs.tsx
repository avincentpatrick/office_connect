import type { ReactNode } from "react";
import { Tabs as RadixTabs } from "radix-ui";

export interface TabItem {
  value: string;
  label: string;
  content: ReactNode;
}

/** ui-standards §3.4 — horizontal, keyboard-navigable (Radix roving tabindex). */
export function Tabs({ items, defaultValue }: { items: TabItem[]; defaultValue?: string }) {
  return (
    <RadixTabs.Root defaultValue={defaultValue ?? items[0]?.value}>
      <RadixTabs.List className="flex gap-1 border-b border-border">
        {items.map((item) => (
          <RadixTabs.Trigger
            key={item.value}
            value={item.value}
            className={
              "min-h-11 border-b-2 border-transparent px-4 text-base text-text-muted " +
              "data-[state=active]:border-brand data-[state=active]:font-medium data-[state=active]:text-text " +
              "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
            }
          >
            {item.label}
          </RadixTabs.Trigger>
        ))}
      </RadixTabs.List>
      {items.map((item) => (
        <RadixTabs.Content key={item.value} value={item.value} className="pt-4">
          {item.content}
        </RadixTabs.Content>
      ))}
    </RadixTabs.Root>
  );
}
