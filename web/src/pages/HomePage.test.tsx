import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderRoutes, stubFetch } from "../test/harness";
import { makeConfig, makeMe } from "../test/auth-fixtures";
import { expectNoA11yViolations } from "../test/a11y";
import { HomePage } from "./HomePage";

const ROUTES = [{ path: "/", element: <HomePage /> }];
const FLAGS_ON = makeConfig({ features: { "module.reimbursement": true } });

const STAFF = ["reimb.claim.create", "reimb.claim.read", "reimb.claim.submit"];
const ADMIN_OFFICER = [
  "reimb.claim.read",
  "reimb.claim.review",
  "reimb.claim.fms_update",
  "reimb.cash_advance.manage",
];

function renderLanding(permissions: string[], config = FLAGS_ON) {
  return renderRoutes(ROUTES, "/", { me: makeMe({ permissions }), config });
}

/**
 * ⚠ `import.meta.env.DEV` is TRUE under vitest, so the `devOnly` "UI
 * foundation" item is openable in every test above — which means a user who can
 * open NOTHING is unreachable in a dev build while that route exists.
 *
 * That is correct behaviour, not a bug: in a dev build the item genuinely is
 * openable, and in production it is statically eliminated. So the no-access
 * state is asserted against the PRODUCTION shape, which is the only shape in
 * which it can occur.
 */
function renderProdLanding(permissions: string[], config = FLAGS_ON) {
  vi.stubEnv("DEV", false);
  return renderLanding(permissions, config);
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("HomePage", () => {
  it("lists what this user can open, and does not list Home", () => {
    renderLanding(ADMIN_OFFICER);
    expect(screen.getByRole("link", { name: /Reimbursement/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Cash advances/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Claim queue/ })).toBeInTheDocument();
    // The front door does not list itself.
    expect(screen.queryByRole("link", { name: "Home" })).not.toBeInTheDocument();
  });

  it("makes no network requests", () => {
    // Decision 4, pinned: stubFetch with no handlers throws on ANY request, so
    // a stray fetch fails the test rather than passing quietly.
    const spy = stubFetch({});
    renderLanding(STAFF);
    expect(screen.getByRole("link", { name: /Reimbursement/ })).toBeInTheDocument();
    expect(spy).not.toHaveBeenCalled();
  });

  it("shows a no-access state and NO query bar when the user can open nothing", () => {
    renderProdLanding([]);
    expect(
      screen.getByText("You do not have access to any modules yet."),
    ).toBeInTheDocument();
    // A search box over an empty index can only ever refuse.
    expect(screen.queryByRole("search")).not.toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("says the modules are switched off — not “ask an administrator” — when flags are OFF", () => {
    renderProdLanding(ADMIN_OFFICER, makeConfig({ features: {} }));
    expect(screen.getByText("No modules are switched on right now.")).toBeInTheDocument();
  });

  it("narrows the list to matches as you type", async () => {
    const user = userEvent.setup();
    renderLanding(ADMIN_OFFICER);
    await user.type(screen.getByLabelText("What do you want to open?"), "queue");

    expect(screen.getByRole("link", { name: /Claim queue/ })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Cash advances/ })).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("1 match for “queue”");
  });

  it("refuses a query that matches nothing and then names everything openable", async () => {
    const user = userEvent.setup();
    renderLanding(ADMIN_OFFICER);
    await user.type(screen.getByLabelText("What do you want to open?"), "zzz");

    expect(screen.getByRole("status")).toHaveTextContent(
      "Nothing matches “zzz”. Here is everything you can open.",
    );
    // ⚠ The likeliest bug in this increment: rendering the openable list TWICE
    // in this state — once as "results", once as "everything you can open" —
    // which duplicates every href and announces every destination twice.
    expect(screen.getAllByRole("link", { name: /Reimbursement/ })).toHaveLength(1);
    expect(screen.getAllByRole("list")).toHaveLength(1);
  });

  it("never offers a destination the user's permissions do not cover", async () => {
    // Decision 3's guarantee at page level: the matcher is handed an
    // already-gated array, so a query for a surface this traveller cannot open
    // produces the refusal — never the link.
    const user = userEvent.setup();
    renderLanding(STAFF);
    await user.type(screen.getByLabelText("What do you want to open?"), "queue");

    expect(screen.getByRole("status")).toHaveTextContent("Nothing matches “queue”");
    expect(screen.queryByRole("link", { name: /Claim queue/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Pipeline board/ })).not.toBeInTheDocument();
  });

  it("has no accessibility violations while listing destinations", async () => {
    const { container } = renderLanding(ADMIN_OFFICER);
    await expectNoA11yViolations(container);
  });

  it("has no accessibility violations in the no-access state", async () => {
    const { container } = renderProdLanding([]);
    await expectNoA11yViolations(container);
  });

  it("has no accessibility violations after a refused query", async () => {
    const user = userEvent.setup();
    const { container } = renderLanding(ADMIN_OFFICER);
    await user.type(screen.getByLabelText("What do you want to open?"), "zzz");
    await expectNoA11yViolations(container);
  });
});
