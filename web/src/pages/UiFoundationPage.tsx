import { useState } from "react";
import { Plus } from "lucide-react";
import { Button } from "../components/Button/Button";
import { Callout } from "../components/Callout/Callout";
import { Card } from "../components/Card/Card";
import { CheckboxField } from "../components/CheckboxField/CheckboxField";
import { ChipGroup } from "../components/ChipGroup/ChipGroup";
import { ConfirmationPanel } from "../components/ConfirmationPanel/ConfirmationPanel";
import { ConfirmDialog } from "../components/Dialog/Dialog";
import { FormDialog } from "../components/Dialog/FormDialog";
import { FileUpload } from "../components/FileUpload/FileUpload";
import { EmptyState } from "../components/EmptyState/EmptyState";
import { ErrorSummary } from "../components/ErrorSummary/ErrorSummary";
import { FormField } from "../components/FormField/FormField";
import { RadioGroupField } from "../components/RadioGroupField/RadioGroupField";
import { SelectField } from "../components/SelectField/SelectField";
import { SummaryList } from "../components/SummaryList/SummaryList";
import { TextareaField } from "../components/TextareaField/TextareaField";
import { WorkItemRow } from "../components/WorkItemRow/WorkItemRow";
import { PipelineCard } from "../components/PipelineCard/PipelineCard";
import { RankedBarList } from "../components/RankedBarList/RankedBarList";
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
  const [chips, setChips] = useState<string[]>(["1"]);
  const [formDialogOpen, setFormDialogOpen] = useState(false);
  const [demoUpload, setDemoUpload] = useState<string>();

  return (
    <AdminPage title="UI foundation">
      <p className="text-base text-text-muted">
        The 19-component inventory and template system on the served design tokens. Development
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
        <div className="flex max-w-2xl gap-3">
          <div className="max-w-xs flex-1">
            <PipelineCard
              refNo="RB-2026-0001"
              title="Iloilo field visit"
              status="waiting"
              statusLabel="For certification"
              meta={`${formatPeso("5500.00")} · J. Dela Cruz`}
            />
          </div>
          {/* R-7-board: the same card with a destination. Spec §9.6 —
              "clicking a card opens the tracker". The link is on the TITLE and
              a stretched overlay makes the whole card clickable, so the
              accessible name stays the title alone. */}
          <div className="max-w-xs flex-1">
            <PipelineCard
              refNo="RB-2026-0002"
              title="Regional immunization review"
              status="blocked"
              statusLabel="Chase FMS"
              meta={`M. Santos · 14 working days with FMS · ${formatPeso("6500.00")}`}
              to="/reimbursement/board"
            />
          </div>
        </div>
      </AdminSection>

      <AdminSection title="9b. Ranked bar list">
        {/* R-8, ui-standards §3.23. Built to the CountdownRing doctrine: the
            bars are aria-hidden decoration and every number is real text, so a
            screen reader hears "12 returns" rather than a rectangle. Bars scale
            against the LARGEST row, never a total — a share of a total would be
            a rate, which this data cannot support. The zero row keeps its place
            and draws no bar at all. */}
        <div className="max-w-xl">
          <RankedBarList
            label="Return reasons, most cited first"
            items={[
              {
                id: 1,
                label: "Missing official receipt",
                count: 12,
                valueText: "12 returns",
                meta: "Up from 7 · Shown as a warning at step 5",
                action: (
                  <Button variant="secondary" className="min-h-11 px-3 py-1 text-sm">
                    Stop warning
                  </Button>
                ),
              },
              {
                id: 2,
                label: "Per-diem miscomputed",
                count: 5,
                valueText: "5 returns",
                meta: "Down from 9",
                action: (
                  <Button variant="secondary" className="min-h-11 px-3 py-1 text-sm">
                    Promote to pre-check
                  </Button>
                ),
              },
              {
                id: 3,
                label: "Obsolete / wrong form version",
                count: 0,
                valueText: "None this period",
                meta: "Down from 4 — none this period",
              },
            ]}
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
        title="15. Form-field family (R-2-wizard)"
        description="Select / Textarea / Checkbox / RadioGroup share FormField's label/help/error contract via the internal FieldChrome."
      >
        <div className="flex max-w-md flex-col gap-4">
          <SelectField
            id="demo-select"
            label="Destination region"
            help="Sets the EO 77 per-diem cluster."
            placeholder="Select a region"
            options={[
              { value: "13", label: "NCR (13)" },
              { value: "01", label: "Region I (01)" },
            ]}
          />
          <TextareaField id="demo-textarea" label="Purpose of travel" />
          <CheckboxField
            id="demo-checkbox"
            label="Lodging was provided by the host"
            hint="EO 77: strips 50% of the day's rate."
          />
          <RadioGroupField
            id="demo-radio"
            name="demo-radio"
            legend="Fund source"
            options={[
              { value: "GF_ORS", label: "General Fund (ORS)" },
              { value: "TF_BUR", label: "Trust Fund (BUR)" },
            ]}
            error="Select the fund source."
          />
        </div>
      </AdminSection>

      <AdminSection title="16. Summary list (check your answers)">
        <SummaryList
          rows={[
            {
              key: "Purpose",
              value: "Regional immunization review",
              action: { label: "Change", to: "#", visuallyHidden: "purpose" },
            },
            { key: "DPO number", value: "" },
          ]}
        />
      </AdminSection>

      <AdminSection title="17. Confirmation panel">
        <ConfirmationPanel
          title="Claim submitted"
          referenceLabel="Your reference number"
          reference="RB-2026-0001"
        />
      </AdminSection>

      <AdminSection title="18. Work-item row (My Work)">
        <ul className="divide-y divide-border border-t border-b border-border">
          <WorkItemRow
            refNo="RB-2026-0001"
            title="Regional immunization review"
            status="waiting"
            statusLabel="For Approval"
            to="#"
            meta={`Holder: Maria Santos · 3 days in this step · ${formatPeso("6750.00")}`}
          />
        </ul>
      </AdminSection>

      <AdminSection title="19. Chip group (multi-select taxonomy)">
        <ChipGroup
          id="demo-chips"
          legend="Why are you returning it?"
          help="Pick every reason that applies."
          options={[
            { value: "1", label: "Missing official receipt" },
            { value: "2", label: "Per-diem miscomputed" },
            { value: "3", label: "Missing required signature" },
          ]}
          value={chips}
          onChange={setChips}
        />
      </AdminSection>

      <AdminSection title="20. Form dialog (a decision that needs input)">
        <Button variant="secondary" onClick={() => setFormDialogOpen(true)}>
          Return claim
        </Button>
        <FormDialog
          open={formDialogOpen}
          onOpenChange={setFormDialogOpen}
          title="Return this claim"
          description="The claim goes back to the claimant to fix and resubmit."
          submitLabel="Return claim"
          danger
          onSubmit={() => {
            setFormDialogOpen(false);
            toast("Claim returned (demo).", "info");
          }}
        >
          <TextareaField id="demo-dialog-comment" label="What needs fixing?" />
        </FormDialog>
      </AdminSection>

      <AdminSection title="21. File upload (R-3)">
        <FileUpload
          id="demo-upload"
          label="Upload your travel order"
          help="Attach a scan or a photo."
          accept="image/jpeg,image/png,image/webp,application/pdf"
          status={demoUpload}
          onFiles={(files) => setDemoUpload(`${files[0].name} attached.`)}
        />
      </AdminSection>

      <AdminSection title="22. Callout (R-3)">
        <div className="flex flex-col gap-3">
          <Callout status="warn" title="1 automatic check flagged">
            <p>
              You can still approve. Approving past a flag is recorded against
              your name.
            </p>
          </Callout>
          <Callout status="blocked" title="Required documents are missing">
            <p>This claim cannot be approved until the claimant attaches them.</p>
          </Callout>
        </div>
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
