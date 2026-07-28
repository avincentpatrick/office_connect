import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { expectNoA11yViolations } from "../../test/a11y";
import { TaskList, type TaskListSection } from "./TaskList";

const SECTIONS: TaskListSection[] = [
  {
    title: "Trip details",
    items: [
      { name: "Travel order", status: "done", statusLabel: "Completed", to: "/wizard/travel-order" },
      { name: "Itinerary", status: "warn", statusLabel: "Not started", to: "/wizard/itinerary" },
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
];

describe("TaskList", () => {
  it("renders numbered sections with per-item status tags", () => {
    render(
      <MemoryRouter>
        <TaskList sections={SECTIONS} />
      </MemoryRouter>,
    );
    expect(screen.getByText("1. Trip details")).toBeInTheDocument();
    expect(screen.getByText("2. Review")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Travel order" })).toHaveAttribute(
      "href",
      "/wizard/travel-order",
    );
    expect(screen.getByText("Cannot start yet")).toBeInTheDocument();
    // Cannot-start items are inert — no link.
    expect(screen.queryByRole("link", { name: "Check your answers" })).toBeNull();
  });

  it("has no axe violations", async () => {
    const { container } = render(
      <MemoryRouter>
        <TaskList sections={SECTIONS} />
      </MemoryRouter>,
    );
    await expectNoA11yViolations(container);
  });
});
