import type { ReactNode } from "react";
import { Navigate, Outlet, useLocation } from "react-router";
import { PageSkeleton } from "../components/Skeleton/Skeleton";
import { AppShell } from "../layouts/AppShell";
import { NotFoundPage } from "../pages/NotFoundPage";
import { isFeatureOn } from "../lib/flags";
import { useAuth } from "./providers/auth-context";
import { useConfig } from "./providers/config-context";

/**
 * Guarded layout route. Mirrors the backend's require_session_pending_ok
 * semantics: a session with must_change_password (then mfa_setup_required) is
 * pinned to its forced page until resolved — this is the bootstrap admin's
 * day-one path: login → change password → enroll MFA → home.
 */
export function RequireAuth() {
  const { me, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) return <PageSkeleton label="Checking your session" />;
  if (!me) return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  if (me.must_change_password && location.pathname !== "/account/password") {
    return <Navigate to="/account/password" replace />;
  }
  if (
    !me.must_change_password &&
    me.mfa_setup_required &&
    location.pathname !== "/account/mfa"
  ) {
    return <Navigate to="/account/mfa" replace />;
  }

  return (
    <AppShell>
      <Outlet />
    </AppShell>
  );
}

/** Route gate on a feature flag — absent key = OFF (fail-safe), rendering NotFound. */
export function RequireFlag({ flag, children }: { flag: string; children: ReactNode }) {
  const { features } = useConfig();
  if (!isFeatureOn(features, flag)) return <NotFoundPage />;
  return <>{children}</>;
}
