import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { expectNoA11yViolations } from "../../test/a11y";
import { WorkItemRow } from "./WorkItemRow";

function renderRow(refNo: string | null = "RB-2026-0001") {
  return render(
    <MemoryRouter>
      <ul>
        <WorkItemRow
          refNo={refNo}
          title="Regional workshop — Manila"
          status="waiting"
          statusLabel="For Approval"
          to="/reimbursement/claims/7"
          meta="Holder: Maria Santos · 3 days in this step · Next: Approve or return"
        />
      </ul>
    </MemoryRouter>,
  );
}

describe("WorkItemRow", () => {
  it("links the reference + title to the claim and shows the status chip", () => {
    renderRow();
    const link = screen.getByRole("link", {
      name: "RB-2026-0001 — Regional workshop — Manila",
    });
    expect(link).toHaveAttribute("href", "/reimbursement/claims/7");
    expect(screen.getByText("For Approval")).toBeInTheDocument();
    expect(screen.getByText(/Maria Santos/)).toBeInTheDocument();
  });

  it("falls back to the bare title for unreferenced drafts", () => {
    renderRow(null);
    expect(
      screen.getByRole("link", { name: "Regional workshop — Manila" }),
    ).toBeInTheDocument();
  });

  it("has no axe violations", async () => {
    const { container } = renderRow();
    await expectNoA11yViolations(container);
  });
});
