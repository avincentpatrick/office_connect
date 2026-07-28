import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "./http";

function jsonResponse(
  status: number,
  body: unknown,
  headers: Record<string, string> = {},
): Response {
  return new Response(body === null ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("api", () => {
  it("sends X-Requested-With on POST (CSRF contract) but not on GET", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    await api("/auth/logout", { method: "POST" });
    await api("/config");

    const postInit = fetchMock.mock.calls[0][1] as RequestInit;
    const getInit = fetchMock.mock.calls[1][1] as RequestInit;
    expect(new Headers(postInit.headers).get("X-Requested-With")).toBe("fetch");
    expect(new Headers(getInit.headers).get("X-Requested-With")).toBeNull();
    expect(postInit.credentials).toBe("same-origin");
    expect(fetchMock.mock.calls[1][0]).toBe("/api/v1/config");
  });

  it("sets Content-Type only when a body is present", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    await api("/auth/login", { method: "POST", body: JSON.stringify({ a: 1 }) });
    await api("/auth/logout", { method: "POST" });

    expect(new Headers((fetchMock.mock.calls[0][1] as RequestInit).headers).get("Content-Type")).toBe(
      "application/json",
    );
    expect(
      new Headers((fetchMock.mock.calls[1][1] as RequestInit).headers).get("Content-Type"),
    ).toBeNull();
  });

  it("throws a typed ApiError from the envelope", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          401,
          {
            error: { code: "invalid_credentials", message: "Invalid email or password." },
            request_id: "abc123",
          },
          { "X-Request-ID": "abc123" },
        ),
      ),
    );

    const error = await api("/auth/login", { method: "POST" }).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    const apiError = error as ApiError;
    expect(apiError.status).toBe(401);
    expect(apiError.code).toBe("invalid_credentials");
    expect(apiError.message).toBe("Invalid email or password.");
    expect(apiError.requestId).toBe("abc123");
    expect(apiError.retryAfter).toBeNull();
  });

  it("parses Retry-After on 429", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          429,
          { error: { code: "too_many_attempts", message: "Too many attempts." } },
          { "Retry-After": "37" },
        ),
      ),
    );

    const error = (await api("/auth/login", { method: "POST" }).catch((e: unknown) => e)) as ApiError;
    expect(error.code).toBe("too_many_attempts");
    expect(error.retryAfter).toBe(37);
  });

  it("degrades to unknown_error on a non-JSON error body", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("<html>bad gateway</html>", { status: 502 })),
    );

    const error = (await api("/config").catch((e: unknown) => e)) as ApiError;
    expect(error.status).toBe(502);
    expect(error.code).toBe("unknown_error");
  });
});
