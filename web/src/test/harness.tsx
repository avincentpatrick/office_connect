/**
 * Shared page-test harness (first page-level tests, R-2-wizard): a memory
 * router + fresh QueryClient, and a keyed fetch stub ("METHOD /path" →
 * handler) following the vi.stubGlobal pattern from api/http.test.ts.
 */

import { render } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, RouterProvider, type RouteObject } from "react-router";
import { vi } from "vitest";

export function renderRoutes(routes: RouteObject[], initialPath: string) {
  const router = createMemoryRouter(routes, { initialEntries: [initialPath] });
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  });
  const utils = render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return { ...utils, router, queryClient };
}

export interface StubResponse {
  status?: number;
  body: unknown;
}

export type FetchHandler = (init?: RequestInit) => StubResponse;

/** Stub global fetch. Keys are "GET /api/v1/…"; unmatched requests throw. */
export function stubFetch(handlers: Record<string, FetchHandler>) {
  const spy = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    const method = init?.method ?? "GET";
    const handler = handlers[`${method} ${url}`];
    if (!handler) {
      throw new Error(`Unstubbed fetch: ${method} ${url}`);
    }
    const { status = 200, body } = handler(init);
    return new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", spy);
  return spy;
}
