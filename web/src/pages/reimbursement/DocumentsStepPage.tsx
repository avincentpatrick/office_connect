import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FileCheck } from "lucide-react";
import { Link, useNavigate } from "react-router";
import { ApiError } from "../../api/http";
import {
  generateClaimDocuments,
  removeChecklistFile,
  reimbKeys,
  uploadChecklistFile,
  type ChecklistItem,
  type ChecklistResponse,
  type ClaimDetail,
} from "../../api/reimbursement";
import { Button } from "../../components/Button/Button";
import { Callout } from "../../components/Callout/Callout";
import { EmptyState } from "../../components/EmptyState/EmptyState";
import { ErrorSummary } from "../../components/ErrorSummary/ErrorSummary";
import { FileUpload } from "../../components/FileUpload/FileUpload";
import { StatusChip } from "../../components/StatusChip/StatusChip";
import {
  TaskList,
  type TaskListItem,
  type TaskListSection,
} from "../../components/TaskList/TaskList";
import { WizardPage } from "../../layouts/WizardPage";
import { formatManilaDate } from "../../lib/format";
import {
  CHECKLIST_GROUP_LABEL,
  CHECKLIST_GROUP_ORDER,
  EVIDENCE_HELP,
  SCAN_NOTE,
  SCAN_PRESENTATION,
  checklistItemAnchor,
  checklistProgress,
  generatedDocHelp,
  itemPresentation,
} from "./checklist-status";
import { ClaimStepGuard } from "./ClaimStepGuard";
import { GeneratedDocCard } from "./GeneratedDocCard";
import { ClaimTotalsCard } from "./MoneyStepPage";
import { useChecklist } from "./use-claim";
import { buildTaskSections, STEP_LABELS, stepNumber, stepPath } from "./wizard-steps";

/** What the browser will offer in the file picker (and the OS camera sheet). */
const ACCEPT = "image/jpeg,image/png,image/webp,application/pdf";

export function DocumentsStepPage() {
  return (
    <ClaimStepGuard slug="documents">
      {(claim) => <DocumentsStep claim={claim} />}
    </ClaimStepGuard>
  );
}

/**
 * Spec §9.3 step 4 — the documentary packet as a GOV.UK task list ("the
 * checklist is the interface", §9.1 principle 2).
 *
 * No UnsavedChangesGuard here, unlike Trip/Itinerary/Money: there is no buffered
 * form state, every upload commits immediately, so there is nothing to lose.
 */
function DocumentsStep({ claim }: { claim: ClaimDetail }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const checklist = useChecklist(claim.id);

  const [busyItem, setBusyItem] = useState<number | null>(null);
  const [itemErrors, setItemErrors] = useState<Record<number, string | undefined>>(
    {},
  );
  const [announce, setAnnounce] = useState<Record<number, string | undefined>>({});
  // Generation is claim-wide, not per item, so its notice and error live beside
  // the per-item ones rather than inside them.
  const [generateNotice, setGenerateNotice] = useState<string | undefined>();
  const [generateError, setGenerateError] = useState<string | undefined>();

  /**
   * Write BOTH caches from the one response: the row list the Documents step
   * renders, and the summary the Review gate and the approver's callouts read.
   * No refetch, so the two can never disagree mid-flight.
   */
  const applyResponse = (response: ChecklistResponse) => {
    queryClient.setQueryData(reimbKeys.checklist(claim.id), response);
    queryClient.setQueryData(
      reimbKeys.claim(claim.id),
      (old: ClaimDetail | undefined) =>
        old ? { ...old, checklist: response.summary } : old,
    );
    // Deliberately no myWork() invalidation: an upload changes no status, no
    // holder, no SLA and no totals — nothing that inbox renders.
  };

  const onMutationError = (error: unknown, catalogId: number) => {
    setItemErrors((prev) => ({
      ...prev,
      // The server's message VERBATIM (ui-standards §3.14): 413 and 422 already
      // carry actionable sentences, and re-writing them here would be the drift
      // the parity rule exists to prevent.
      [catalogId]:
        error instanceof ApiError
          ? error.message
          : "Something went wrong. Please try again.",
    }));
    setAnnounce((prev) => ({ ...prev, [catalogId]: undefined }));
    if (error instanceof ApiError && error.status === 409) {
      // The claim moved under us. The claim(id) prefix sweeps the checklist and
      // the timeline too — the one place that key nesting earns its keep.
      void queryClient.invalidateQueries({ queryKey: reimbKeys.claim(claim.id) });
    }
  };

  const upload = useMutation({
    mutationFn: ({ catalogId, file }: { catalogId: number; file: File }) =>
      uploadChecklistFile(claim.id, catalogId, file),
    onMutate: ({ catalogId, file }) => {
      setBusyItem(catalogId);
      setItemErrors((prev) => ({ ...prev, [catalogId]: undefined }));
      setAnnounce((prev) => ({ ...prev, [catalogId]: `Uploading ${file.name}…` }));
    },
    onSuccess: (response, { catalogId, file }) => {
      applyResponse(response);
      setAnnounce((prev) => ({
        ...prev,
        [catalogId]: `${file.name} attached. We are checking the file.`,
      }));
    },
    onError: (error, { catalogId }) => onMutationError(error, catalogId),
    onSettled: () => setBusyItem(null),
  });

  const remove = useMutation({
    mutationFn: ({ catalogId, fileId }: { catalogId: number; fileId: number }) =>
      removeChecklistFile(claim.id, catalogId, fileId),
    onMutate: ({ catalogId }) => setBusyItem(catalogId),
    onSuccess: (response, { catalogId }) => {
      applyResponse(response);
      setAnnounce((prev) => ({ ...prev, [catalogId]: "File removed." }));
    },
    onError: (error, { catalogId }) => onMutationError(error, catalogId),
    onSettled: () => setBusyItem(null),
  });

  /**
   * Ask the server to prepare the generated documents.
   *
   * Rendering runs in the worker, so the 202 response cannot contain the
   * finished PDFs — it reports whether the job was accepted. The rows arrive on
   * the next checklist read, which is why success invalidates rather than
   * writing the response straight into the cache the way the upload path does.
   */
  const generate = useMutation({
    mutationFn: () => generateClaimDocuments(claim.id),
    onMutate: () => setGenerateError(undefined),
    onSuccess: (response) => {
      applyResponse(response.checklist);
      setGenerateNotice(
        response.queued
          ? "We are preparing your documents. They appear here in a moment."
          : // §19.12: never a 500, never a blocked submit — an honest notice.
            "Document preparation is unavailable right now. Your claim is saved and you can still submit; the documents are prepared when the service is back.",
      );
      // The worker writes rows this request cannot see. One delayed refetch is
      // enough for a packet that takes about a second to render, and it beats
      // a polling loop that would keep running long after the user has left.
      window.setTimeout(() => {
        void queryClient.invalidateQueries({
          queryKey: reimbKeys.checklist(claim.id),
        });
      }, 2500);
    },
    onError: (error) => {
      setGenerateNotice(undefined);
      setGenerateError(
        error instanceof ApiError
          ? error.message
          : "Something went wrong. Please try again.",
      );
    },
  });

  const shell = (children: React.ReactNode) => (
    <WizardPage
      title="File a travel claim"
      steps={STEP_LABELS}
      current={stepNumber("documents")}
      back={
        <Link
          to={stepPath(claim.id, "money")}
          className="text-sm text-link underline"
        >
          Back to Money
        </Link>
      }
      taskList={<TaskList sections={buildTaskSections(claim)} />}
      asideExtra={claim.totals ? <ClaimTotalsCard totals={claim.totals} /> : undefined}
    >
      <section aria-labelledby="documents-heading" className="flex flex-col gap-4">
        <h2 id="documents-heading" className="text-xl font-bold text-text">
          Your documents
        </h2>
        {children}
      </section>
    </WizardPage>
  );

  const continueButton = (
    <div>
      {/* Always enabled — Documents never traps you. The gate is on Review
          (spec §9.3 step 5), where the blocking items are listed inline. */}
      <Button onClick={() => navigate(stepPath(claim.id, "review"))}>
        Continue to review
      </Button>
    </div>
  );

  if (checklist.isPending) {
    return shell(
      <div role="status" aria-busy="true">
        <span className="sr-only">Loading your documents…</span>
        <div className="flex flex-col gap-3">
          <div className="h-12 animate-pulse rounded bg-surface" />
          <div className="h-12 animate-pulse rounded bg-surface" />
          <div className="h-12 animate-pulse rounded bg-surface" />
        </div>
      </div>,
    );
  }

  if (checklist.isError) {
    return shell(
      <>
        <ErrorSummary
          errors={[
            {
              message:
                checklist.error instanceof ApiError
                  ? checklist.error.message
                  : "Something went wrong. Please try again.",
            },
          ]}
        />
        {/* Never a dead end (§9.1 principle 4) — the way forward stays open. */}
        {continueButton}
      </>,
    );
  }

  const { items, summary } = checklist.data;

  if (items.length === 0) {
    return shell(
      <EmptyState
        icon={FileCheck}
        title="No documents are required for this claim"
        description="Nothing to attach. You can go straight to the review step."
        action={continueButton}
      />,
    );
  }

  const renderItem = (item: ChecklistItem): Pick<TaskListItem, "detail" | "action"> => {
    const uploadable =
      item.evidence === "upload" || item.evidence === "external_wet_sign";
    const generated = item.evidence === "generated_doc";
    const noteId = `checklist-note-${item.catalog_id}`;

    const detail = (
      <div className="flex flex-col gap-1">
        {/* Server-authored prose, rendered verbatim — it cites claim data and
            circulars the client cannot see. */}
        {item.required_because ? <span>{item.required_because}</span> : null}
        {item.flag_reason ? (
          <span className="font-medium text-status-warn">{item.flag_reason}</span>
        ) : null}
        {!uploadable ? (
          <span id={noteId}>
            {generated ? generatedDocHelp(item) : EVIDENCE_HELP[item.evidence]}
          </span>
        ) : null}
        {/* Generated PDFs are rendered by the card in the action slot, never as
            file rows: they are not evidence the claimant supplied and must not
            offer a Remove button — the system owns them. */}
        {!generated && item.files.length > 0 ? (
          <ul className="mt-1 flex flex-col gap-2">
            {item.files.map((file) => {
              const scan = SCAN_PRESENTATION[file.scan_status];
              const note = SCAN_NOTE[file.scan_status];
              return (
                <li key={file.id} className="flex flex-col gap-1">
                  <div className="flex flex-wrap items-center gap-2">
                    {file.download_path ? (
                      <a
                        href={file.download_path}
                        className="text-base text-link underline"
                      >
                        {file.filename}
                      </a>
                    ) : (
                      // No link until the scan is clean — the file exists but
                      // is not servable, and a dangling URL would 409.
                      <span className="text-base text-text">{file.filename}</span>
                    )}
                    <StatusChip status={scan.status}>{scan.label}</StatusChip>
                  </div>
                  <span>Uploaded {formatManilaDate(file.uploaded_at)}</span>
                  {note ? <span>{note}</span> : null}
                  <div>
                    <Button
                      variant="secondary"
                      onClick={() =>
                        remove.mutate({
                          catalogId: item.catalog_id,
                          fileId: file.id,
                        })
                      }
                    >
                      Remove<span className="sr-only"> {file.filename}</span>
                    </Button>
                  </div>
                </li>
              );
            })}
          </ul>
        ) : null}
      </div>
    );

    if (generated) {
      return {
        detail,
        action: <GeneratedDocCard item={item} busy={generate.isPending} />,
      };
    }

    if (!uploadable) return { detail };

    return {
      detail,
      action: (
        <FileUpload
          id={`upload-${item.catalog_id}`}
          label={
            item.evidence === "external_wet_sign"
              ? "Upload the signed page"
              : `Upload ${item.label}`
          }
          help={EVIDENCE_HELP[item.evidence] ?? undefined}
          accept={ACCEPT}
          // `capture` deliberately unset: spec §9.3 says camera capture is
          // ALLOWED, and on mobile `capture` forces the camera and deletes the
          // gallery option. `accept` already surfaces Camera beside Files.
          busy={busyItem === item.catalog_id}
          error={itemErrors[item.catalog_id]}
          status={announce[item.catalog_id]}
          onFiles={(files) =>
            upload.mutate({ catalogId: item.catalog_id, file: files[0] })
          }
        />
      ),
    };
  };

  const sections: TaskListSection[] = CHECKLIST_GROUP_ORDER.flatMap((group) => {
    const rows = items
      .filter((item) => item.group === group)
      .sort((a, b) => a.sort - b.sort || a.code.localeCompare(b.code));
    if (rows.length === 0) return []; // never an empty heading
    return [
      {
        title: CHECKLIST_GROUP_LABEL[group],
        items: rows.map((item) => {
          const presentation = itemPresentation(item);
          return {
            id: checklistItemAnchor(item.catalog_id),
            // Plain language primary, verbatim legal wording secondary
            // (spec §9.1 principle 3).
            name: item.label,
            hint: item.code,
            status: presentation.status,
            statusLabel: presentation.label,
            ...renderItem(item),
          };
        }),
      },
    ];
  });

  const hasGeneratedDocs = items.some((item) => item.evidence === "generated_doc");

  return shell(
    <>
      {/* Present from mount so only CHANGES announce (spec §9.1's progress line). */}
      <p aria-live="polite" className="text-base font-medium text-text">
        {checklistProgress(summary)}
      </p>
      {generateError ? (
        <Callout status="blocked" title="We could not prepare your documents">
          {/* The server's sentence verbatim (ui-standards §3.14) — it names the
              actual reason, e.g. that the Money step is not finished. */}
          {generateError}
        </Callout>
      ) : null}
      {generateNotice ? (
        <Callout status="waiting" title="Preparing your documents" live="polite">
          {generateNotice}
        </Callout>
      ) : null}
      <TaskList sections={sections} />
      {hasGeneratedDocs ? (
        <div>
          <Button
            variant="secondary"
            loading={generate.isPending}
            onClick={() => generate.mutate()}
          >
            Prepare my documents
          </Button>
          <p className="mt-1 text-sm text-text-muted">
            {/* Says the quiet part out loud: this button is a convenience, not a
                gate. Generated documents are excluded from the submit check by
                design, and the packet is regenerated at submit anyway. */}
            The system fills these in from what you entered. They are prepared
            again when you submit, so the filed copies always match your claim.
          </p>
        </div>
      ) : null}
      {continueButton}
    </>,
  );
}
