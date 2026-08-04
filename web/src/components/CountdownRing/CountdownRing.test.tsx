import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { expectNoA11yViolations } from "../../test/a11y";
import { CountdownRing } from "./CountdownRing";

describe("CountdownRing", () => {
  it("states every fact in text, not only in the ring", () => {
    // §6: status by text + colour, never colour alone. The arc encodes urgency
    // twice (sweep and hue) and neither is available without sight.
    render(
      <CountdownRing
        daysRemaining={12}
        state="on_track"
        deadlineDate="2026-08-02"
      />,
    );
    expect(screen.getByText("On track")).toBeInTheDocument();
    expect(screen.getByText(/12 days left/)).toBeInTheDocument();
    expect(screen.getByText(/Aug 2, 2026/)).toBeInTheDocument();
  });

  it("hides the decorative svg from assistive technology", () => {
    const { container } = render(
      <CountdownRing
        daysRemaining={3}
        state="due_soon"
        deadlineDate="2026-08-02"
      />,
    );
    const svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("aria-hidden", "true");
    expect(svg).toHaveAttribute("focusable", "false");
  });

  it("renders an honest 'not started' when there is no deadline", () => {
    // A full ring would read as plenty of time and an empty one as overdue.
    render(
      <CountdownRing daysRemaining={null} state={null} deadlineDate={null} />,
    );
    expect(
      screen.getByText("No liquidation deadline yet"),
    ).toBeInTheDocument();
  });

  it("counts up once past the deadline", () => {
    render(
      <CountdownRing
        daysRemaining={-4}
        state="overdue"
        deadlineDate="2026-08-02"
      />,
    );
    expect(screen.getByText("Overdue")).toBeInTheDocument();
    expect(screen.getByText(/4 days overdue/)).toBeInTheDocument();
  });

  it("says 'day' not 'days' at one", () => {
    render(
      <CountdownRing
        daysRemaining={1}
        state="due_soon"
        deadlineDate="2026-08-02"
      />,
    );
    expect(screen.getByText(/1 day left/)).toBeInTheDocument();
  });

  it("clamps the arc rather than winding backwards when overdue", () => {
    const { container } = render(
      <CountdownRing
        daysRemaining={-90}
        state="overdue"
        deadlineDate="2026-08-02"
      />,
    );
    const arc = container.querySelectorAll("circle")[1];
    const dashArray = Number(arc.getAttribute("stroke-dasharray"));
    const offset = Number(arc.getAttribute("stroke-dashoffset"));
    expect(offset).toBeCloseTo(dashArray, 5); // fully empty, never negative
  });

  it("has no axe violations in any state", async () => {
    const { container } = render(
      <div>
        <CountdownRing
          daysRemaining={20}
          state="on_track"
          deadlineDate="2026-08-02"
        />
        <CountdownRing
          daysRemaining={3}
          state="due_soon"
          deadlineDate="2026-08-02"
          size="md"
        />
        <CountdownRing
          daysRemaining={-2}
          state="overdue"
          deadlineDate="2026-08-02"
        />
        <CountdownRing daysRemaining={null} state={null} deadlineDate={null} />
      </div>,
    );
    await expectNoA11yViolations(container);
  });
});
