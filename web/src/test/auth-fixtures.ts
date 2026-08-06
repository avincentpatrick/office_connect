/**
 * Shared auth/config test fixtures.
 *
 * `makeMe` lived inside `app/guards.test.tsx` until Stage D-1 needed a second
 * consumer. Promoted here rather than copied: a per-file `MeResponse` literal
 * is how fixtures drift, and the field that would drift first is
 * `permissions` — the one the nav now gates on.
 */

import type { ConfigResponse, MeResponse } from "../api/types";

export function makeMe(overrides: Partial<MeResponse> = {}): MeResponse {
  return {
    user_id: 1,
    email: "admin@example.gov.ph",
    roles: ["admin"],
    permissions: [],
    idle_tier: "privileged",
    is_privileged: true,
    must_change_password: false,
    mfa_authenticated: true,
    mfa_setup_required: false,
    session: {
      session_id_hash: "abc",
      created_at: "2026-07-28T00:00:00Z",
      last_seen_at: "2026-07-28T00:00:00Z",
      ip: null,
      user_agent: null,
      current: true,
    },
    ...overrides,
  };
}

export function makeConfig(overrides: Partial<ConfigResponse> = {}): ConfigResponse {
  return {
    tenant: { name: "Test Tenant", short_name: "TT", timezone: "Asia/Manila" },
    branding: {},
    tokens: {},
    features: {},
    version: "0.0.0-test",
    ...overrides,
  };
}
