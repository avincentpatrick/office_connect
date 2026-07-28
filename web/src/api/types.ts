/**
 * Response types for the /api/v1 surface the shell consumes. Typed from the
 * backend pydantic schemas (office_connect/core/api/schemas/auth.py and
 * core/api/config.py) — field names are the wire names.
 */

export type TokenLeaf = string | number;
export interface TokenTree {
  [key: string]: TokenLeaf | TokenTree;
}

export interface TenantInfo {
  name: string;
  short_name: string;
  timezone: string;
}

/** GET /api/v1/config — public, never 500s; absent feature key = OFF. */
export interface ConfigResponse {
  tenant: TenantInfo;
  branding: Record<string, unknown>;
  tokens: TokenTree;
  features: Record<string, boolean>;
  version: string;
}

export type LoginStatus =
  | "authenticated"
  | "mfa_required"
  | "password_change_required"
  | "mfa_setup_required";

export interface LoginResponse {
  status: LoginStatus;
  user_id: number | null;
  must_change_password: boolean;
  mfa_setup_required: boolean;
  mfa_token: string | null;
}

export interface SessionSummary {
  session_id_hash: string;
  created_at: string;
  last_seen_at: string;
  ip: string | null;
  user_agent: string | null;
  current: boolean;
}

export interface MeResponse {
  user_id: number;
  email: string;
  roles: string[];
  idle_tier: string;
  is_privileged: boolean;
  must_change_password: boolean;
  mfa_authenticated: boolean;
  mfa_setup_required: boolean;
  session: SessionSummary;
}

export interface MfaEnrollResponse {
  secret: string;
  otpauth_uri: string;
}

export interface OkResponse {
  ok: boolean;
}

/** 422 validation detail rows ({loc, msg, type} — input/ctx stripped server-side). */
export interface ValidationDetail {
  loc: (string | number)[];
  msg: string;
  type: string;
}

/** The canonical error envelope (core/api/errors.py). */
export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details?: unknown;
  };
  request_id?: string;
}
