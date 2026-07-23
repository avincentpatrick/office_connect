# API & Observability Standards

Binding conventions for the HTTP API surface and runtime observability.
Introduced Increment 4 (Stage A / Phase 0); the `/api/v1/` prefix has been the
de-facto convention since Increment 1 (`GET /api/v1/config`).

## §1. API versioning

- **Every application endpoint lives under a version prefix: `/api/v1/…`.**
  Health/liveness (`/health`) and the root (`/`) are unversioned operational
  endpoints.
- **Additive within a major version.** New endpoints, new optional request
  fields, and new response fields may be added under `v1` without a version
  bump — clients must ignore unknown response fields.
- **Breaking changes require a new major prefix (`/api/v2/`).** Removing/renaming
  a field, changing a type, tightening validation, or changing status-code
  semantics is breaking. `v1` and `v2` coexist during a documented deprecation
  window.
- **Never break a shipped contract in place.** Version, don't mutate.
- Routers are mounted from `office_connect/core/api/` (core) and, later, per
  module — each under `/api/v1/<area>`.

## §2. Request/response conventions

- **`X-Request-ID`** — every request is tagged with a request id (honored from an
  inbound `X-Request-ID`, else generated). It is echoed on the response and flows
  into structured logs and the audit context (`created_by`/actor arrives with
  auth in Stage B).
- **JSON only** for request and response bodies (`application/json`); file
  downloads stream bytes with the correct `Content-Type` + `Content-Disposition`.
- **Money is server-computed**; the API returns computed `numeric(12,2)` values
  and formatted strings — the client never does money math (database-standards
  §10).
- **Times are UTC ISO-8601** on the wire (`timestamptz`); the client renders
  Asia/Manila (core/time.py).
- **Config never 500s** — `/api/v1/config` is fail-safe and returns all feature
  flags OFF under any backend degradation (never leaks non-public `settings`).

## §3. Error envelope

Error responses use a consistent shape so clients branch on `error.code`, not on
prose:

```json
{ "error": { "code": "validation_error", "message": "human-readable summary",
             "details": [ ... ] }, "request_id": "…" }
```

- HTTP status carries the class (400/401/403/404/409/422/500); `error.code` is a
  stable machine slug. Never leak DSNs, hostnames, stack traces, or SPI in an
  error body (the `/health` endpoint already exposes only the exception *type*).

## §4. Observability

- **Structured JSON logs** (`core/logging.py`): one JSON object per line with
  `ts` (UTC), `level`, `logger`, `message`, and `request_id` when set. Toggle to
  human-readable with `LOG_JSON=false`. `LOG_LEVEL` sets the threshold.
- **Request-id propagation**: the request-id middleware sets a `ContextVar` so
  every log emitted while handling a request carries its id.
- **Self-hosted error tracker** (`core/observability.py`): Sentry-SDK compatible
  (GlitchTip). **Fail-safe optional** — active only when `SENTRY_DSN` is set; no
  DSN is a no-op and a bad DSN never crashes startup. GlitchTip runs behind the
  compose `observability` profile (not in the default stack); full production
  hardening is a Stage-C/deploy task.
- **Celery operability** (master-plan §3.2): tasks use `acks_late`, bounded
  `max_retries` + back-off, and a dead-letter concept — notification dispatch
  moves exhausted rows to `status='dead'` with an append-only
  `core_notification_deliveries` trail (the failed-jobs substrate). Beat is a
  single instance.

## §5. Deferred to later stages

- **AuthN/AuthZ** (Stage B): bearer/session auth, RBAC, per-route permission
  checks, and the real actor on `created_by`/audit. Until then, protected
  surfaces (e.g. the attachments upload/download router) are built as service
  methods with an injected authorization hook, not exposed HTTP routes.
- **Rate limiting, pagination envelope, WebSocket channels** (Stage D+) as the
  first real read/write endpoints land.
