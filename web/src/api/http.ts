import type { ApiErrorBody } from "./types";

/**
 * The one fetch wrapper (api-standards §6). Every API call goes through here:
 * - same-origin credentials — the oc_session cookie is Path=/api, and dev runs
 *   behind the Vite proxy so the browser is always same-origin (no CORS).
 * - X-Requested-With on EVERY non-safe method (including POST /auth/login) —
 *   the CSRF middleware rejects mutating requests without it (403 csrf_failed).
 * - Errors are the typed envelope {error:{code,message,details}, request_id};
 *   the X-Request-ID header is surfaced for support.
 */
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly details: unknown,
    public readonly requestId: string | null,
    public readonly retryAfter: number | null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);
const BASE = "/api/v1";

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (!SAFE_METHODS.has(method)) headers.set("X-Requested-With", "fetch");
  // FormData is exempt: only the browser knows the multipart boundary it is
  // about to generate, so a hand-set Content-Type breaks the upload. FormData is
  // the only non-JSON body this app sends — a speculative Blob/URLSearchParams
  // allowlist would be untested code (api-standards §6).
  if (
    init.body != null &&
    !headers.has("Content-Type") &&
    !(init.body instanceof FormData)
  ) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${BASE}${path}`, {
    ...init,
    method,
    headers,
    credentials: "same-origin",
  });

  const body: unknown =
    response.status === 204 ? null : await response.json().catch(() => null);

  if (!response.ok) {
    const envelope = (body ?? {}) as Partial<ApiErrorBody>;
    const retryAfter = response.headers.get("Retry-After");
    throw new ApiError(
      response.status,
      envelope.error?.code ?? "unknown_error",
      envelope.error?.message ?? "Something went wrong. Please try again.",
      envelope.error?.details ?? null,
      response.headers.get("X-Request-ID"),
      retryAfter !== null && !Number.isNaN(Number(retryAfter)) ? Number(retryAfter) : null,
    );
  }

  return body as T;
}
