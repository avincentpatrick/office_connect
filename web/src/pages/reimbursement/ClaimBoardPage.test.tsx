import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, within } from "@testing-library/react";
import { reimbKeys } from "../../api/reimbursement";
import { expectNoA11yViolations } from "../../test/a11y";
import { renderRoutes, stubFetch } from "../../test/harness";
import {
  makeBoardColumn,
  makeClaimBoard,
  makeQueueItem,
} from "../../test/reimb-fixtures";
import { ClaimBoardPage } from "./ClaimBoardPage";

const ROUTES = [{ path: "/reimbursement/board", element: <ClaimBoardPage /> }];

// Exact-URL key: the harness throws on an unstubbed request, so this IS the
// assertion that the page asks for `/board` and not `/claims/board` — the
// literal segment that FastAPI would read as a claim id.
const BOARD = "GET /api/v1/reimbursement/board";

afterEach(() => vi.unstubAllGlobals());

describe("ClaimBoardPage", () => {
  it("heads every column with its count and its peso total", async () => {
    stubFetch({ [BOARD]: () => ({ body: makeClaimBoard() }) });
    const { container } = renderRoutes(ROUTES, "/reimbursement/board");

    expect(await screen.findByRole("heading", { name: "In Bureau" })).toBeInTheDocument();
    expect(screen.getByText("1 claim · ₱4,200.00")).toBeInTheDocument();
    // The heading itself carries only the name — a screen-reader heading list
    // must read "With FMS", not "With FMS 1 ₱6,750.00".
    expect(screen.getByRole("heading", { name: "With FMS" })).toBeInTheDocument();
    expect(screen.getByText("1 claim · ₱6,750.00")).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it("says the Done column is a window, using the server's number", async () => {
    stubFetch({
      [BOARD]: () => ({ body: makeClaimBoard({ done_window_days: 45 }) }),
    });
    renderRoutes(ROUTES, "/reimbursement/board");
    expect(
      await screen.findByRole("heading", { name: "Done · last 45 days" }),
    ).toBeInTheDocument();
  });

  it("renders an empty column as ₱0.00 rather than hiding it", async () => {
    // "Nothing has closed" is an answer. A column that disappeared would leave
    // a chief wondering whether it failed to load.
    stubFetch({ [BOARD]: () => ({ body: makeClaimBoard() }) });
    renderRoutes(ROUTES, "/reimbursement/board");

    await screen.findByRole("heading", { name: "In Bureau" });
    expect(screen.getByText("0 claims · ₱0.00")).toBeInTheDocument();
    expect(screen.getByText("Nothing has closed in this period.")).toBeInTheDocument();
  });

  it("opens the tracker from a card, named by its title alone", async () => {
    // Spec §9.6: "clicking a card opens the tracker". The accessible name is
    // the TITLE — not ref + chip + title + meta fused into one enormous link
    // name, which is what wrapping the whole card in an anchor would give.
    stubFetch({ [BOARD]: () => ({ body: makeClaimBoard() }) });
    renderRoutes(ROUTES, "/reimbursement/board");

    const link = await screen.findByRole("link", {
      name: "Regional immunization review",
    });
    expect(link).toHaveAttribute("href", "/reimbursement/claims/7");
  });

  it("dates a Done card by when it closed, never '0 days in this step'", async () => {
    // A terminal claim has no holder and no `holder_since`, so `days_in_state`
    // is 0. The queue never had to handle that — it has no terminal rows — and
    // reusing its wording would print "0 days" on a claim paid weeks ago.
    stubFetch({
      [BOARD]: () => ({
        body: makeClaimBoard({
          columns: [
            makeBoardColumn({ key: "in_bureau", label: "In Bureau", items: [] }),
            makeBoardColumn({ key: "with_fms", label: "With FMS", items: [] }),
            makeBoardColumn({
              key: "done",
              label: "Done",
              items: [
                makeQueueItem({
                  id: 42,
                  ref_no: "RB-2026-0042",
                  status: "paid_closed",
                  status_label: "Paid / Closed",
                  next_action: null,
                  holder_kind: null,
                  holder_display: null,
                  holder_since: null,
                  days_in_state: 0,
                  days_with_fms: null,
                  // R-7-events leaves the last FMS event on a paid claim. It
                  // must not surface here: "Last: With Accounting" on a closed
                  // claim reads as still pending.
                  external_status_label: "With Accounting",
                  updated_at: "2026-07-15T02:00:00Z",
                }),
              ],
            }),
          ],
        }),
      }),
    });
    renderRoutes(ROUTES, "/reimbursement/board");

    expect(await screen.findByText(/Closed Jul 15, 2026/)).toBeInTheDocument();
    expect(screen.queryByText(/0 days in this step/)).not.toBeInTheDocument();
    expect(screen.queryByText(/With Accounting/)).not.toBeInTheDocument();
  });

  it("states what a capped column is hiding, quoting the server's count", async () => {
    stubFetch({
      [BOARD]: () => ({
        body: makeClaimBoard({
          columns: [
            makeBoardColumn({
              key: "in_bureau",
              label: "In Bureau",
              count: 137,
              total: "890500.00",
            }),
            makeBoardColumn({ key: "with_fms", label: "With FMS", items: [] }),
            makeBoardColumn({ key: "done", label: "Done", items: [] }),
          ],
        }),
      }),
    });
    renderRoutes(ROUTES, "/reimbursement/board");

    expect(await screen.findByText(/Showing 1 of 137\./)).toBeInTheDocument();
    // The header is the WHOLE column, so it keeps saying 137 while one card
    // shows — that gap is the point of the surface.
    expect(screen.getByText("137 claims · ₱890,500.00")).toBeInTheDocument();
  });

  it("never re-derives a total from the cards it can see", async () => {
    // The fixture deliberately disagrees with itself: one ₱6,500 card under a
    // ₱1,284,300.00 header. The server summed the whole column in SQL; the page
    // displays money and never adds it up (tech-stack §4).
    stubFetch({
      [BOARD]: () => ({
        body: makeClaimBoard({
          columns: [
            makeBoardColumn({
              key: "in_bureau",
              label: "In Bureau",
              count: 198,
              total: "1284300.00",
            }),
            makeBoardColumn({ key: "with_fms", label: "With FMS", items: [] }),
            makeBoardColumn({ key: "done", label: "Done", items: [] }),
          ],
        }),
      }),
    });
    renderRoutes(ROUTES, "/reimbursement/board");
    expect(await screen.findByText("198 claims · ₱1,284,300.00")).toBeInTheDocument();
  });

  it("floats the chase chip where the server flagged one", async () => {
    stubFetch({
      [BOARD]: () => ({
        body: makeClaimBoard({
          columns: [
            makeBoardColumn({ key: "in_bureau", label: "In Bureau", items: [] }),
            makeBoardColumn({
              items: [makeQueueItem({ days_with_fms: 3, external_followup: true })],
            }),
            makeBoardColumn({ key: "done", label: "Done", items: [] }),
          ],
        }),
      }),
    });
    renderRoutes(ROUTES, "/reimbursement/board");
    expect(await screen.findByText("Chase FMS")).toBeInTheDocument();
  });

  it("shows one empty state when the whole board is empty", async () => {
    stubFetch({
      [BOARD]: () => ({
        body: makeClaimBoard({
          columns: [
            makeBoardColumn({ key: "in_bureau", label: "In Bureau", items: [], total: "0.00" }),
            makeBoardColumn({ items: [], total: "0.00" }),
            makeBoardColumn({ key: "done", label: "Done", items: [], total: "0.00" }),
          ],
        }),
      }),
    });
    const { container } = renderRoutes(ROUTES, "/reimbursement/board");

    expect(await screen.findByText("Nothing is in the pipeline")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "In Bureau" })).not.toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it("renders the server's own refusal for an actor who oversees nobody", async () => {
    // A board leaks a division's whole budget in one integer, so the 403 here
    // matters more than on the queue. Its message names My Work; the page must
    // not paraphrase it into a second copy to keep true.
    stubFetch({
      [BOARD]: () => ({
        status: 403,
        body: {
          error: {
            code: "reimb_queue_not_permitted",
            message:
              "This queue shows other people's claims, so it is for approvers and the Admin Officer. Your own claims are on My Work.",
          },
        },
      }),
    });
    const { container } = renderRoutes(ROUTES, "/reimbursement/board");

    expect(await screen.findByText("This board is not yours to see")).toBeInTheDocument();
    expect(screen.getByText(/Your own claims are on My Work/)).toBeInTheDocument();
    await expectNoA11yViolations(container);
  });

  it("keeps a card's chip and meta out of its link name", async () => {
    stubFetch({ [BOARD]: () => ({ body: makeClaimBoard() }) });
    renderRoutes(ROUTES, "/reimbursement/board");

    const card = (await screen.findByText("RB-2026-0001")).closest("article");
    expect(card).not.toBeNull();
    const links = within(card as HTMLElement).getAllByRole("link");
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAccessibleName("Regional immunization review");
  });
});

describe("the board's query key", () => {
  it("sits under the queues() prefix so a write invalidates it", () => {
    // `FmsStatusDialog` and `MarkPaidDialog` invalidate `reimbKeys.queues()`.
    // A `mark_paid` moves a claim from With FMS to Done — a board key outside
    // that prefix would make this the one screen still showing the claim where
    // it was a moment ago, immediately after the button that moved it.
    const prefix = reimbKeys.queues();
    expect(reimbKeys.board().slice(0, prefix.length)).toEqual([...prefix]);
  });
});
