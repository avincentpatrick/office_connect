/**
 * Shared page-test harness (first page-level tests, R-2-wizard): a memory
 * router + fresh QueryClient, and a keyed fetch stub ("METHOD /path" →
 * handler) following the vi.stubGlobal pattern from api/http.test.ts.
 */

import { render } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, RouterProvider, type RouteObject } from "react-router";
import { vi } from "vitest";
import type { ConfigResponse, MeResponse } from "../api/types";
import { AuthContext } from "../app/providers/auth-context";
import { ConfigContext } from "../app/providers/config-context";

export interface RenderRoutesOptions {
  /** Supply to wrap in AuthContext — a page that reads `useAuth()` needs it. */
  me?: MeResponse | null;
  /** Supply to wrap in ConfigContext — a page that reads `useConfig()` needs it. */
  config?: ConfigResponse;
}

export function renderRoutes(
  routes: RouteObject[],
  initialPath: string,
  options: RenderRoutesOptions = {},
) {
  const router = createMemoryRouter(routes, { initialEntries: [initialPath] });
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  });
  // Contexts are opt-in: pages that fetch through TanStack Query need neither,
  // and wrapping unconditionally would hide a page accidentally depending on one.
  let tree = <RouterProvider router={router} />;
  if ("me" in options) {
    tree = (
      <AuthContext.Provider value={{ me: options.me ?? null, isLoading: false }}>
        {tree}
      </AuthContext.Provider>
    );
  }
  if (options.config) {
    tree = <ConfigContext.Provider value={options.config}>{tree}</ConfigContext.Provider>;
  }
  const utils = render(
    <QueryClientProvider client={queryClient}>{tree}</QueryClientProvider>,
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
