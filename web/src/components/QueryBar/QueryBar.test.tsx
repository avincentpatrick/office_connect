import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ReceiptText } from "lucide-react";
import { renderRoutes } from "../../test/harness";
import { expectNoA11yViolations } from "../../test/a11y";
import { QueryBar, type QueryBarProps } from "./QueryBar";

const RESULTS = [
  { id: "/reimbursement", label: "Reimbursement", to: "/reimbursement", icon: ReceiptText, meta: "File a claim." },
  { id: "/reimbursement/queue", label: "Claim queue", to: "/reimbursement/queue" },
];

function renderBar(overrides: Partial<QueryBarProps> = {}) {
  const props: QueryBarProps = {
    label: "What do you want to open?",
    value: "",
    onValueChange: vi.fn(),
    resultsHeading: "What you can open",
    results: RESULTS,
    statusText: "",
    ...overrides,
  };
  const utils = renderRoutes(
    [
      { path: "/", element: <QueryBar {...props} /> },
      { path: "/reimbursement", element: <p>reimbursement page</p> },
    ],
    "/",
  );
  return { ...utils, props };
}

describe("QueryBar", () => {
  it("labels the field with a real <label>, not a placeholder", () => {
    renderBar({ placeholder: "Try “travel”" });
    // getByLabelText only resolves through a real label association.
    expect(screen.getByLabelText("What do you want to open?")).toBeInTheDocument();
  });

  it("exposes a search landmark", () => {
    renderBar();
    expect(screen.getByRole("search")).toBeInTheDocument();
  });

  it("leaves the landmark unnamed unless asked, so no two nodes share one name", () => {
    // Naming the landmark with the field's label would make getByLabelText —
    // and a screen reader's own element lists — ambiguous between the region
    // and the control inside it.
    renderBar();
    expect(screen.getByRole("search")).not.toHaveAttribute("aria-label");
  });

  it("renders results as links in a list", () => {
    renderBar();
    const list = screen.getByRole("list");
    expect(list).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Reimbursement/ })).toHaveAttribute(
      "href",
      "/reimbursement",
    );
  });

  it("announces the status sentence in a polite live region", () => {
    renderBar({ statusText: "2 matches for “claim”. Choose one below." });
    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("2 matches for “claim”. Choose one below.");
    expect(status).toHaveAttribute("aria-live", "polite");
  });

  it("describes the input with the status sentence", () => {
    renderBar({ statusText: "Nothing matches “zzz”." });
    expect(screen.getByLabelText("What do you want to open?")).toHaveAccessibleDescription(
      "Nothing matches “zzz”.",
    );
  });

  it("renders only the status sentence when there are no results", () => {
    renderBar({ results: [], statusText: "Nothing matches “zzz”." });
    // No empty <ul>, and no heading dangling over nothing.
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "What you can open" })).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Nothing matches “zzz”.");
  });

  it("does not use combobox semantics", () => {
    // THIS TEST IS THE INVENTORY ROW'S CONTRACT (ui-standards §3.24). The pull
    // toward a combobox is strong and the failure is invisible to sighted
    // testing, so the prohibition is asserted rather than merely written down.
    renderBar();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("option")).not.toBeInTheDocument();
    const input = screen.getByLabelText("What do you want to open?");
    expect(input).not.toHaveAttribute("aria-expanded");
    expect(input).not.toHaveAttribute("aria-activedescendant");
    expect(input).not.toHaveAttribute("aria-autocomplete");
  });

  it("does not mark an unmatched query as a validation error", () => {
    renderBar({ results: [], value: "zzz", statusText: "Nothing matches “zzz”." });
    // A true answer is not a mistake the user made.
    expect(screen.getByLabelText("What do you want to open?")).not.toHaveAttribute(
      "aria-invalid",
    );
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("clears the query on Escape and keeps focus in the field", async () => {
    const user = userEvent.setup();
    const onValueChange = vi.fn();
    renderBar({ value: "queue", onValueChange });
    const input = screen.getByLabelText("What do you want to open?");
    await user.click(input);
    await user.keyboard("{Escape}");
    expect(onValueChange).toHaveBeenCalledWith("");
    expect(input).toHaveFocus();
  });

  it("does not navigate on Enter", async () => {
    const user = userEvent.setup();
    const { router } = renderBar({ value: "reimb" });
    await user.click(screen.getByLabelText("What do you want to open?"));
    await user.keyboard("{Enter}");
    expect(router.state.location.pathname).toBe("/");
  });

  it("has no accessibility violations", async () => {
    const { container } = renderBar({ statusText: "2 matches. Choose one below." });
    await expectNoA11yViolations(container);
  });
});
