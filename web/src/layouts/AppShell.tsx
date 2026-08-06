import { useState, type ReactNode } from "react";
import { Link, NavLink, useNavigate } from "react-router";
import { LogOut, Menu, X } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { logout } from "../api/auth";
import { NotificationBell } from "../components/Toast/Toast";
import { ME_QUERY_KEY, useAuth } from "../app/providers/auth-context";
import { useConfig } from "../app/providers/config-context";
import { visibleNavItems } from "../app/nav";
import { cx } from "../lib/cx";

function navLinkClass({ isActive }: { isActive: boolean }): string {
  return cx(
    "inline-flex min-h-11 items-center gap-2 rounded-md px-3 text-base text-brand-contrast",
    "hover:bg-brand-contrast/10",
    "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-contrast",
    isActive && "font-bold underline underline-offset-4",
  );
}

/**
 * ui-standards §4.1 — App shell: top bar + NAV_GROUPS nav + content slot.
 * Every page renders inside it. `minimal` (login/MFA screens) shows the brand
 * bar only. Mobile nav is a disclosure below md (phone-first, §6).
 */
export function AppShell({
  minimal = false,
  children,
}: {
  minimal?: boolean;
  children: ReactNode;
}) {
  const { tenant, features } = useConfig();
  const { me } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [mobileOpen, setMobileOpen] = useState(false);

  const signOut = useMutation({
    mutationFn: logout,
    onSettled: () => {
      queryClient.setQueryData(ME_QUERY_KEY, null);
      navigate("/login", { replace: true });
    },
  });

  const items = minimal || !me ? [] : visibleNavItems(features, me.permissions);

  return (
    <div className="flex min-h-screen flex-col bg-bg">
      <a
        href="#main"
        className="sr-only rounded-md bg-brand px-3 py-2 text-brand-contrast focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50"
      >
        Skip to main content
      </a>
      <header className="bg-brand text-brand-contrast shadow-sm">
        <div className="mx-auto flex min-h-14 w-full max-w-5xl items-center justify-between gap-4 px-4">
          <div className="flex items-center gap-4">
            <Link
              to="/"
              className="inline-flex min-h-11 items-center text-lg font-bold focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-contrast"
            >
              {tenant.name}
            </Link>
            {items.length > 0 ? (
              <nav aria-label="Main" className="hidden items-center gap-1 md:flex">
                {items.map((item) => (
                  <NavLink key={item.to} to={item.to} end={item.to === "/"} className={navLinkClass}>
                    <item.icon aria-hidden="true" className="size-4" />
                    {item.label}
                  </NavLink>
                ))}
              </nav>
            ) : null}
          </div>
          {!minimal && me ? (
            <div className="flex items-center gap-1">
              <NotificationBell />
              <span className="hidden text-sm sm:inline">{me.email}</span>
              <button
                type="button"
                onClick={() => signOut.mutate()}
                disabled={signOut.isPending}
                className="inline-flex min-h-11 items-center gap-1 rounded-md px-3 text-sm hover:bg-brand-contrast/10 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-contrast"
              >
                <LogOut aria-hidden="true" className="size-4" />
                Sign out
              </button>
              {items.length > 0 ? (
                <button
                  type="button"
                  className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-md hover:bg-brand-contrast/10 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-contrast md:hidden"
                  aria-expanded={mobileOpen}
                  aria-controls="mobile-nav"
                  aria-label={mobileOpen ? "Close menu" : "Open menu"}
                  onClick={() => setMobileOpen((open) => !open)}
                >
                  {mobileOpen ? (
                    <X aria-hidden="true" className="size-5" />
                  ) : (
                    <Menu aria-hidden="true" className="size-5" />
                  )}
                </button>
              ) : null}
            </div>
          ) : null}
        </div>
        {mobileOpen && items.length > 0 ? (
          <nav
            id="mobile-nav"
            aria-label="Main"
            className="flex flex-col gap-1 border-t border-brand-contrast/20 px-4 py-2 md:hidden"
          >
            {items.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                className={navLinkClass}
                onClick={() => setMobileOpen(false)}
              >
                <item.icon aria-hidden="true" className="size-4" />
                {item.label}
              </NavLink>
            ))}
          </nav>
        ) : null}
      </header>
      <main id="main" className="mx-auto w-full max-w-5xl flex-1 p-4 md:p-6">
        {children}
      </main>
    </div>
  );
}
