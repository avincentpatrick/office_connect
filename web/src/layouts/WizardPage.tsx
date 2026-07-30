import type { ReactNode } from "react";
import { Stepper } from "../components/Stepper/Stepper";

export interface WizardPageProps {
  title: string;
  steps: string[];
  /** 1-based active step. */
  current: number;
  /** Back affordance (back-safe navigation), rendered above the title. */
  back?: ReactNode;
  /** Task-list sidebar (§3.6) — stacks below lg. */
  taskList: ReactNode;
  /** Extra rail content below the task list (spec §9.3 running-totals card). */
  asideExtra?: ReactNode;
  children: ReactNode;
}

/** ui-standards §4.3 — Wizard page: stepper shell + one step's form + task-list sidebar. */
export function WizardPage({
  title,
  steps,
  current,
  back,
  taskList,
  asideExtra,
  children,
}: WizardPageProps) {
  return (
    <div className="flex flex-col gap-4">
      {back}
      <h1 className="text-2xl font-bold text-text">{title}</h1>
      <div className="grid gap-8 lg:grid-cols-[2fr_1fr]">
        <div className="flex flex-col gap-6">
          <Stepper steps={steps} current={current} />
          <div>{children}</div>
        </div>
        <aside aria-label="Progress checklist" className="flex flex-col gap-6">
          {taskList}
          {asideExtra}
        </aside>
      </div>
    </div>
  );
}
