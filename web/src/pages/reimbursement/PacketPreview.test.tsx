import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expectNoA11yViolations } from "../../test/a11y";
import { renderRoutes, stubFetch } from "../../test/harness";
import { awaitingApproval, makeClaim, makePacket } from "../../test/reimb-fixtures";
import { canPreparePacket } from "./claim-status";
import { PacketPreview } from "./PacketPreview";

const GENERATE = "POST /api/v1/reimbursement/claims/7/documents/generate";

function render(claim = awaitingApproval(), canPrepare = false) {
  return renderRoutes(
    [{ path: "/x", element: <PacketPreview claim={claim} canPrepare={canPrepare} /> }],
    "/x",
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("PacketPreview — spec §9.2's packet PDF preview", () => {
  it("offers the link at every width and the frame only from lg", async () => {
    const packet = makePacket();
    const { container } = render(awaitingApproval({ packet }));

    const link = screen.getByRole("link", { name: /Open the packet/ });
    expect(link).toHaveAttribute("href", packet.download_path);
    expect(link).toHaveAttribute("target", "_blank");
    // An unannounced context switch is a WCAG 3.2.5 failure.
    expect(link).toHaveTextContent("opens in a new tab");

    // The frame is the DESKTOP enhancement over the link — iOS Safari will not
    // render a PDF in an iframe, and §9.2 marks this surface phone-first.
    const frame = container.querySelector("iframe");
    expect(frame).toHaveAttribute("title", "Claim packet preview");
    expect(frame).toHaveAttribute("src", packet.download_path);
    expect(frame?.className).toContain("hidden");
    expect(frame?.className).toContain("lg:block");

    await expectNoA11yViolations(container);
  });

  it("says which copy this is — draft or filed", async () => {
    render(awaitingApproval({ packet: makePacket({ is_draft: true }) }));
    expect(screen.getByText("Draft copy")).toBeInTheDocument();
    // Not colour alone: the sentence spells out what a draft copy means.
    expect(
      screen.getByText(/no reference number and is not the filed document/),
    ).toBeInTheDocument();
  });

  it("marks the post-submit packet as the filed copy", async () => {
    render(awaitingApproval({ packet: makePacket({ is_draft: false }) }));
    expect(screen.getByText("Filed copy")).toBeInTheDocument();
  });

  it("explains the absence instead of showing an empty frame", async () => {
    const { container } = render(awaitingApproval({ packet: null }));

    expect(container.querySelector("iframe")).toBeNull();
    expect(screen.getByText(/has not been prepared yet/)).toBeInTheDocument();
    // No button for someone who may not ask — the UI is never offered a
    // control certain to 403 (the R-4-screens doctrine).
    expect(
      screen.queryByRole("button", { name: "Prepare the packet" }),
    ).not.toBeInTheDocument();
  });

  it("lets an actor who may act ask for one, and reports a worker outage", async () => {
    // §19.12: `queued: false` is not an error. The notice is honest and the
    // decision buttons elsewhere on the page stay live.
    stubFetch({ [GENERATE]: () => ({ status: 202, body: { queued: false } }) });
    render(awaitingApproval({ packet: null }), true);

    await userEvent.click(screen.getByRole("button", { name: "Prepare the packet" }));
    expect(
      await screen.findByText(/Document preparation is unavailable right now/),
    ).toBeInTheDocument();
    // Never a dead end: the claim is explicitly described as still decidable.
    expect(screen.getByText(/you can still decide on it/)).toBeInTheDocument();
  });

  it("reports a queued render without pretending the PDF has arrived", async () => {
    stubFetch({ [GENERATE]: () => ({ status: 202, body: { queued: true } }) });
    render(awaitingApproval({ packet: null }), true);

    await userEvent.click(screen.getByRole("button", { name: "Prepare the packet" }));
    expect(
      await screen.findByText(/We are preparing the packet/),
    ).toBeInTheDocument();
  });

  it("shows the server's refusal verbatim", async () => {
    // ui-standards §3.14 — the client authors no gate wording, so there is
    // nothing to drift from the server's sentence.
    stubFetch({
      [GENERATE]: () => ({
        status: 422,
        body: {
          error: { code: "reimb_totals_missing", message: "Finish the Money step first." },
        },
      }),
    });
    render(awaitingApproval({ packet: null }), true);

    await userEvent.click(screen.getByRole("button", { name: "Prepare the packet" }));
    expect(
      await screen.findByText("Finish the Money step first."),
    ).toBeInTheDocument();
  });
});

describe("canPreparePacket", () => {
  it("follows the server's action set, not the status", () => {
    expect(canPreparePacket(makeClaim({ available_actions: ["submit", "cancel"] }))).toBe(
      true,
    );
    expect(canPreparePacket(awaitingApproval())).toBe(true); // approve/return
    // A bystander watching a claim at a gate may read it and nothing else.
    expect(canPreparePacket(awaitingApproval({ available_actions: [] }))).toBe(false);
    expect(canPreparePacket(makeClaim({ available_actions: ["cancel"] }))).toBe(false);
  });
});
