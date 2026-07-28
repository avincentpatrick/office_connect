import { useState } from "react";
import { Plus } from "lucide-react";
import { Button } from "../components/Button/Button";
import { Card } from "../components/Card/Card";
import { ConfirmDialog } from "../components/Dialog/Dialog";
import { EmptyState } from "../components/EmptyState/EmptyState";
import { ErrorSummary } from "../components/ErrorSummary/ErrorSummary";
import { FormField } from "../components/FormField/FormField";
import { PipelineCard } from "../components/PipelineCard/PipelineCard";
import { Skeleton } from "../components/Skeleton/Skeleton";
import { StatusChip } from "../components/StatusChip/StatusChip";
import { Stepper } from "../components/Stepper/Stepper";
import { Tabs } from "../components/Tabs/Tabs";
import { TaskList } from "../components/TaskList/TaskList";
import { Timeline } from "../components/Timeline/Timeline";
import { toast } from "../components/Toast/toast-bus";
import { AdminPage, AdminSection } from "../layouts/AdminPage";
import { formatManilaDate, formatPeso } from "../lib/format";

/**
 * DEV-only living catalog of the component inventory (ui-standards §3) and
 * layout templates (§4) — the recorded alternative to Storybook (§7). Route
 * is registered only in development builds.
 */
export function UiFoundationPage() {
  const [fieldValue, setFieldValue] = useState("");

  return (
    <AdminPage title="UI foundation">
      <p className="text-base text-text-muted">
        The 14-component inventory and template system on the served design tokens. Development
        builds only.
      </p>

      <AdminSection title="1. Button">
        <div className="flex flex-wrap gap-2">
          <Button>Primary</Button>
          <Button variant="secondary">Secondary</Button>
          <Button variant="danger">Danger</Button>
          <Button disabled>Disabled</Button>
          <Button loading>Loading</Button>
        </div>
      </AdminSection>

      <AdminSection title="2. Form field">
        <div className="flex max-w-md flex-col gap-4">
          <FormField
            id="demo-ok"
            label="Destination"
            help="City or municipality of official travel."
            value={fieldValue}
            onChange={(event) => setFieldValue(event.target.value)}
          />
          <FormField
            id="demo-error"
            label="Amount"
            error="Enter the fare amount from your official receipt."
            defaultValue="abc"
            required
          />
        </div>
      </AdminSection>

      <AdminSection title="3. Card">
        <Card
          title="Travel claim RB-2026-0001"
          status={<StatusChip status="warn">Due soon</StatusChip>}
          actions={<Button variant="secondary">Open</Button>}
        >
          <p>
            {formatPeso("5500.00")} · filed {formatManilaDate("2026-07-20T02:00:00Z")}
          </p>
        </Card>
      </AdminSection>

      <AdminSection title="4. Tabs">
        <Tabs
          items={[
            { value: "details", label: "Details", content: <p>Trip details content.</p> },
            { value: "history", label: "History", content: <p>Approval history content.</p> },
          ]}
        />
      </AdminSection>

      <AdminSection title="5. Status chip">
        <div className="flex flex-wrap gap-2">
          <StatusChip status="done">Completed</StatusChip>
          <StatusChip status="warn">Due soon</StatusChip>
          <StatusChip status="blocked">Overdue</StatusChip>
          <StatusChip status="waiting">Waiting on external</StatusChip>
        </div>
      </AdminSection>

      <AdminSection title="6. Task list (GOV.UK)">
        <TaskList
          sections={[
            {
              title: "Trip details",
              items: [
                { name: "Travel order", status: "done", statusLabel: "Completed", to: "#" },
                { name: "Itinerary", status: "warn", statusLabel: "Not started", to: "#" },
              ],
            },
            {
              title: "Review",
              items: [
                {
                  name: "Check your answers",
                  status: "waiting",
                  statusLabel: "Cannot start yet",
                  hint: "Complete trip details first.",
                },
              ],
            },
          ]}
        />
      </AdminSection>

      <AdminSection title="7. Stepper / wizard shell">
        <Stepper steps={["Trip", "Legs", "Expenses", "Review"]} current={2} />
      </AdminSection>

      <AdminSection title="8. Timeline / tracker">
        <Timeline
          events={[
            {
              id: 1,
              actor: "J. Dela Cruz",
              timestamp: "2026-07-20T01:00:00Z",
              description: "Claim submitted",
            },
            {
              id: 2,
              actor: "M. Santos",
              timestamp: "2026-07-21T05:30:00Z",
              description: "Certified by supervisor",
            },
          ]}
        />
      </AdminSection>

      <AdminSection title="9. Pipeline-board card">
        <div className="max-w-xs">
          <PipelineCard
            refNo="RB-2026-0001"
            title="Iloilo field visit"
            status="waiting"
            statusLabel="For certification"
            meta={`${formatPeso("5500.00")} · J. Dela Cruz`}
          />
        </div>
      </AdminSection>

      <AdminSection title="10. Dialog / confirm sheet">
        <ConfirmDialog
          trigger={<Button variant="danger">Cancel claim</Button>}
          title="Cancel this claim?"
          consequence="The claim will be withdrawn. You can file a new claim later, but this reference number will not be reused."
          confirmLabel="Cancel the claim"
          danger
          onConfirm={() => toast("Claim cancelled (demo).", "info")}
        />
      </AdminSection>

      <AdminSection title="11. Empty state">
        <EmptyState
          title="Your travel claims will appear here"
          description="Create a claim to get started."
          action={
            <Button>
              <Plus aria-hidden="true" className="size-4" />
              New claim
            </Button>
          }
        />
      </AdminSection>

      <AdminSection title="12. Skeleton loader">
        <div className="flex flex-col gap-2">
          <Skeleton variant="row" />
          <Skeleton />
        </div>
      </AdminSection>

      <AdminSection title="13. Toast / notification bell">
        <div className="flex gap-2">
          <Button variant="secondary" onClick={() => toast("Saved.", "success")}>
            Show success toast
          </Button>
          <Button variant="secondary" onClick={() => toast("Heads up.", "info")}>
            Show info toast
          </Button>
        </div>
      </AdminSection>

      <AdminSection title="14. Error summary (GOV.UK)">
        <ErrorSummary
          errors={[
            { message: "Enter the fare amount from your official receipt", fieldId: "demo-error" },
          ]}
        />
      </AdminSection>

      <AdminSection
        title="Layout templates"
        description="App shell (this chrome), Admin/settings (this page), List, Wizard, Detail + right rail, and Board — see ui-standards §4. The List/Wizard/Detail/Board templates are exercised by their consuming pages as modules arrive."
      >
        <p className="text-sm text-text-muted">
          Pages render only through the layout components in <code>src/layouts/</code>.
        </p>
      </AdminSection>
    </AdminPage>
  );
}
