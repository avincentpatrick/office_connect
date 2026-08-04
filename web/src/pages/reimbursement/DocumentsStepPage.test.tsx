import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expectNoA11yViolations } from "../../test/a11y";
import { renderRoutes, stubFetch } from "../../test/harness";
import {
  documentsPending,
  makeChecklist,
  makeChecklistFile,
  makeChecklistItem,
  makeChecklistSummary,
  makeGeneratedFile,
} from "../../test/reimb-fixtures";
import { DocumentsStepPage } from "./DocumentsStepPage";

const ROUTES = [
  {
    path: "/reimbursement/claims/:claimId/documents",
    element: <DocumentsStepPage />,
  },
  { path: "/reimbursement/claims/:claimId/review", element: <p>Review step</p> },
];

const CLAIM = "GET /api/v1/reimbursement/claims/7";
const CHECKLIST = "GET /api/v1/reimbursement/claims/7/checklist";
const UPLOAD_TO_01 =
  "POST /api/v1/reimbursement/claims/7/checklist/1/attachments";

const jpeg = () => new File(["bytes"], "travel-order.jpg", { type: "image/jpeg" });

afterEach(() => vi.unstubAllGlobals());

function render(checklistBody: unknown = makeChecklist(), extra = {}) {
  const spy = stubFetch({
    [CLAIM]: () => ({ body: documentsPending() }),
    [CHECKLIST]: () => ({ body: checklistBody }),
    ...extra,
  });
  renderRoutes(ROUTES, "/reimbursement/claims/7/documents");
  return spy;
}

describe("DocumentsStepPage", () => {
  it("groups the packet by catalog group and shows the progress line", async () => {
    render();
    // Await a heading the PACKET renders — the progress line alone would
    // resolve early against the wizard rail's copy of it.
    expect(
      await screen.findByRole("heading", { name: /Authority to travel/ }),
    ).toBeInTheDocument();
    // …and once loaded it appears twice on purpose: above the packet, and as
    // the Documents hint in the rail (spec §9.1 "always-visible progress line").
    expect(screen.getAllByText("0 of 2 required items done")).toHaveLength(2);
    expect(
      screen.getByRole("heading", { name: /Proof of travel/ }),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Itinerary/ })).toBeInTheDocument();
    // Groups with no applicable items never render an empty heading.
    expect(
      screen.queryByRole("heading", { name: /Lodging and meals/ }),
    ).not.toBeInTheDocument();
  });

  it("offers an upload for human evidence and none for generated documents", async () => {
    render();
    expect(
      await screen.findByLabelText(/Upload Approved Travel Order/),
    ).toBeInTheDocument();
    // external_wet_sign uploads the SIGNED page — same control, different copy.
    expect(screen.getByLabelText(/Upload the signed page/)).toBeInTheDocument();
    // generated_doc: still nothing to upload, but the copy no longer promises a
    // packet that does not exist — and it says the claimant is not blocked.
    expect(
      screen.getByText(/you can still submit without it/),
    ).toBeInTheDocument();
    expect(
      screen.queryByLabelText(/Upload Itinerary of Travel/),
    ).not.toBeInTheDocument();
  });

  it("uploads as multipart and refreshes the row and the progress line", async () => {
    const attached = {
      items: [
        makeChecklistItem({
          item_id: 55,
          status: "attached",
          files: [makeChecklistFile()],
        }),
      ],
      summary: makeChecklistSummary({ required_total: 2, required_done: 1 }),
    };
    const spy = render(makeChecklist(), {
      [UPLOAD_TO_01]: () => ({ status: 201, body: attached }),
    });

    await userEvent.upload(
      await screen.findByLabelText(/Upload Approved Travel Order/),
      jpeg(),
    );

    // Both the packet's progress line and the rail hint move, from the ONE
    // response — the two caches are written together, never refetched apart.
    await waitFor(() =>
      expect(screen.getAllByText("1 of 2 required items done")).toHaveLength(2),
    );

    const call = spy.mock.calls.find(([url]) => String(url).endsWith("/attachments"));
    const init = call?.[1] as RequestInit;
    expect(init.body).toBeInstanceOf(FormData);
    // The browser must set the multipart boundary itself.
    expect(new Headers(init.headers).get("Content-Type")).toBeNull();
  });

  it("tells the truth about a file that is saved but not yet downloadable", async () => {
    render({
      items: [
        makeChecklistItem({
          item_id: 55,
          status: "attached",
          files: [makeChecklistFile()],
        }),
      ],
      summary: makeChecklistSummary({ required_total: 1, required_done: 1 }),
    });

    // Two chips, deliberately: the ITEM is attached, the FILE is still checking.
    expect(await screen.findByText("Attached")).toBeInTheDocument();
    expect(screen.getByText("Checking")).toBeInTheDocument();
    expect(
      screen.getByText(/It is saved and counts towards your packet/),
    ).toBeInTheDocument();
    // No link while the scan is unfinished — it would 409.
    expect(
      screen.queryByRole("link", { name: "travel-order.jpg" }),
    ).not.toBeInTheDocument();
  });

  it("renders a generated document as a Generated card with a preview link", async () => {
    render({
      items: [
        makeChecklistItem({
          catalog_id: 3,
          item_id: 60,
          code: "IOT-45",
          label: "Itinerary of Travel (GAM App 45)",
          group: "itinerary",
          evidence: "generated_doc",
          status: "generated",
          sort: 3,
          files: [makeGeneratedFile()],
        }),
      ],
      summary: makeChecklistSummary({ required_total: 1, required_done: 0 }),
    });

    // Exactly one "Generated" chip — the task-list row's. The card deliberately
    // does not repeat it (a generated file has no separate scan state).
    await waitFor(() => expect(screen.getAllByText("Generated")).toHaveLength(1));
    // The card states WHEN it was prepared; the help line states what it is.
    expect(screen.getByText("Prepared Aug 3, 2026")).toBeInTheDocument();
    expect(
      screen.getByText(/Check it before you submit/),
    ).toBeInTheDocument();
    const link = screen.getByRole("link", {
      name: /Preview Itinerary of Travel/,
    });
    // Inline disposition is what makes this a preview rather than a download,
    // and it is decided server-side from the row's provenance.
    expect(link).toHaveAttribute("href", "/api/v1/attachments/210/content");
    expect(link).toHaveAttribute("target", "_blank");
    // The system owns generated files — offering Remove would invite a claimant
    // to delete a document they cannot recreate.
    expect(
      screen.queryByRole("button", { name: /Remove/ }),
    ).not.toBeInTheDocument();
    await expectNoA11yViolations(document.body);
  });

  it("degrades non-blockingly when no worker is available to render", async () => {
    render(makeChecklist(), {
      "POST /api/v1/reimbursement/claims/7/documents/generate": () => ({
        status: 202,
        body: { checklist: makeChecklist(), queued: false },
      }),
    });

    await userEvent.click(
      await screen.findByRole("button", { name: "Prepare my documents" }),
    );

    // Spec §19.12: the claim is saved, submission is unaffected, and the user is
    // told plainly — never a 500 and never a spinner that cannot resolve.
    expect(
      await screen.findByText(/Document preparation is unavailable right now/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Continue to review" }),
    ).toBeEnabled();
  });

  it("surfaces the server's reason when the claim is not ready to generate", async () => {
    render(makeChecklist(), {
      "POST /api/v1/reimbursement/claims/7/documents/generate": () => ({
        status: 422,
        body: {
          error: {
            code: "reimb_totals_missing",
            message:
              "The claim's amounts have not been worked out yet — complete the Money step, then the packet can be generated.",
          },
        },
      }),
    });

    await userEvent.click(
      await screen.findByRole("button", { name: "Prepare my documents" }),
    );

    // Verbatim (ui-standards §3.14) — it names the actual next action.
    expect(
      await screen.findByText(/complete the Money step/),
    ).toBeInTheDocument();
  });

  it("shows a rejected upload inline on its own item, never as an ErrorSummary", async () => {
    // ErrorSummary focuses on mount and would rip focus off the input the
    // claimant is standing on.
    render(makeChecklist(), {
      [UPLOAD_TO_01]: () => ({
        status: 422,
        body: {
          error: {
            code: "attachment_rejected",
            message: "The file type is not allowed.",
          },
        },
      }),
    });

    await userEvent.upload(
      await screen.findByLabelText(/Upload Approved Travel Order/),
      jpeg(),
    );

    // The SERVER's sentence, verbatim (ui-standards §3.14).
    expect(
      await screen.findByText("The file type is not allowed."),
    ).toBeInTheDocument();
    expect(screen.queryByText("There is a problem")).not.toBeInTheDocument();
    // The sibling item is untouched.
    expect(screen.getByLabelText(/Upload the signed page/)).toBeEnabled();
  });

  it("offers a way forward when the packet is empty", async () => {
    render({ items: [], summary: makeChecklistSummary() });
    expect(
      await screen.findByText("No documents are required for this claim"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Continue to review" }),
    ).toBeInTheDocument();
  });

  it("keeps a way forward even when the checklist fails to load", async () => {
    render(undefined, {
      [CHECKLIST]: () => ({
        status: 500,
        body: { error: { code: "internal_error", message: "Server error." } },
      }),
    });
    expect(await screen.findByText("There is a problem")).toBeInTheDocument();
    // §9.1 principle 4 — never a dead end.
    expect(
      screen.getByRole("button", { name: "Continue to review" }),
    ).toBeInTheDocument();
  });

  it("never traps the claimant: Continue is always enabled", async () => {
    render();
    const button = await screen.findByRole("button", {
      name: "Continue to review",
    });
    expect(button).toBeEnabled();
    await userEvent.click(button);
    await waitFor(() =>
      expect(screen.getByText("Review step")).toBeInTheDocument(),
    );
  });
});
