import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, RouterProvider } from "react-router";
import type { MeResponse } from "../api/types";
import { makeMe } from "../test/auth-fixtures";
import { AuthContext } from "./providers/auth-context";
import { RequireAuth } from "./guards";

function renderAt(path: string, me: MeResponse | null) {
  const router = createMemoryRouter(
    [
      { path: "/login", element: <p>login page</p> },
      {
        element: <RequireAuth />,
        children: [
          { path: "/", element: <p>home page</p> },
          { path: "/account/password", element: <p>password page</p> },
          { path: "/account/mfa", element: <p>mfa page</p> },
        ],
      },
    ],
    { initialEntries: [path] },
  );
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <AuthContext.Provider value={{ me, isLoading: false }}>
        <RouterProvider router={router} />
      </AuthContext.Provider>
    </QueryClientProvider>,
  );
}

describe("RequireAuth", () => {
  it("redirects unauthenticated visitors to /login", () => {
    renderAt("/", null);
    expect(screen.getByText("login page")).toBeInTheDocument();
  });

  it("pins a must_change_password session to the forced password page", () => {
    renderAt("/", makeMe({ must_change_password: true }));
    expect(screen.getByText("password page")).toBeInTheDocument();
  });

  it("pins an mfa_setup_required session to the forced MFA page after the password gate", () => {
    renderAt("/", makeMe({ mfa_setup_required: true, mfa_authenticated: false }));
    expect(screen.getByText("mfa page")).toBeInTheDocument();
  });

  it("renders the requested page inside the shell for a normal session", () => {
    renderAt("/", makeMe());
    expect(screen.getByText("home page")).toBeInTheDocument();
    expect(screen.getByRole("main")).toBeInTheDocument();
  });
});
