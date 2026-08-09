"""Security response headers (Stage D closeout) — api-standards §10.

**Until this landed the app set none at all.** A repo-wide search for
``Content-Security-Policy``, ``X-Frame-Options``, ``frame-ancestors``,
``Referrer-Policy`` or HSTS returned zero hits; the only security header anywhere
was ``X-Content-Type-Options: nosniff`` on the attachment download route. The
belief that the reverse proxy supplied the rest was unwritten, untested, and had
no config file in this repo to inspect (tech-stack §7a). It is the app's job now,
because the app is the part the suite can pin — the proxy is deployment-time and
post-development.

**Two policies, because the app serves two kinds of thing.** Almost every
response here is JSON or a streamed PDF, and for those ``default-src 'none'`` is
not merely safe but exactly right: they should load nothing, frame nothing and
submit nowhere. Three surfaces are real HTML — ``/docs``, ``/redoc`` and the
audit verification report — and each needs inline scripts or styles to render at
all. Rather than weaken one policy until it fits the loosest surface, the loose
policy is named, scoped to those paths, and kept where anyone can see what it
costs.

**What the CSP here does NOT cover: the SPA.** FastAPI never serves the SPA
document — Vite does in dev, the reverse proxy does in production (api-standards
§6). ``script-src`` and ``style-src`` emitted from here therefore govern only the
surfaces above. The policy the proxy must serve alongside ``index.html`` is a
separate obligation, written down in api-standards §10 so it stops being folklore.

**Two traps this file is deliberately shaped around**, both read off the code
that would have broken:

1. ``frame-ancestors`` is ``'self'``, never ``'none'``, and ``X-Frame-Options``
   is ``SAMEORIGIN``, never ``DENY``. ``PacketPreview.tsx`` embeds the generated
   claim packet in an ``<iframe>``, served from this origin by
   ``/api/v1/attachments/{id}/content``; its own comment says the frame renders
   only because no frame-blocking header is set. ``frame-src`` — the directive
   §7a named — binds the *embedding* document, which is the SPA and not ours.
   ``frame-ancestors`` binds the *embedded* PDF, which is ours. Only the second
   one was ever in this file's power to get wrong.
2. ``X-Content-Type-Options`` is assigned, never appended. ``attachments.py``
   already sets it on the download route, and ``MutableHeaders.append`` would
   ship ``nosniff, nosniff`` on exactly the responses that most need the header
   to be unambiguous.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

#: JSON and streamed bytes: load nothing, frame nothing, submit nowhere. The
#: only permission granted is being framed by our own SPA — trap 1 above.
API_CSP = (
    "default-src 'none'; frame-ancestors 'self'; base-uri 'none'; form-action 'none'"
)

#: The three HTML surfaces this app actually serves. Swagger UI and ReDoc boot
#: from an inline <script> and fetch their assets from jsDelivr; the audit
#: verification report (``core/api/audit.py``) renders an inline <style> block.
#: Nothing here is a nonce candidate: the inline script is FastAPI's own,
#: emitted by ``get_swagger_ui_html`` where we cannot thread a per-request value.
HTML_CSP = (
    "default-src 'none'; frame-ancestors 'self'; base-uri 'none'; form-action 'none'; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "img-src 'self' data: https://fastapi.tiangolo.com; font-src 'self' data:"
)

#: Exact paths served as HTML. A prefix match would be wrong: ``/docs`` must not
#: relax ``/docs-anything-else`` a later stage adds.
HTML_PATHS: frozenset[str] = frozenset(
    {"/docs", "/docs/oauth2-redirect", "/redoc", "/api/v1/audit/verify"}
)

#: Features this platform never uses. Naming them denies them to any embedded
#: content and to anything a future dependency might try.
PERMISSIONS_POLICY = (
    "accelerometer=(), autoplay=(), camera=(), display-capture=(), "
    "encrypted-media=(), fullscreen=(self), geolocation=(), gyroscope=(), "
    "magnetometer=(), microphone=(), midi=(), payment=(), usb=()"
)

#: Send the full path same-origin (support needs it), only the origin on the way
#: out, and nothing at all when downgrading to http.
REFERRER_POLICY = "strict-origin-when-cross-origin"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Set the security headers on every response, including error envelopes.

    Registered OUTSIDE ``CSRFMiddleware`` (see ``main.py``) so a 403 from CSRF
    and a 401 from a protected route carry the same headers a 200 does. A
    security header that is present only on the happy path is the kind of thing
    a scanner reports as passing and an attacker reports as absent.

    Configuration arrives as constructor kwargs rather than a ``get_settings()``
    call in ``dispatch``, for a testability reason worth stating: ``get_settings``
    is ``lru_cache``d and ``main.py`` resolves it once at import, so an
    env-var-driven test could never observe the production shape. Explicit kwargs
    make the production shape a two-line unit test.
    """

    def __init__(
        self,
        app,
        *,
        hsts: bool,
        hsts_max_age: int,
        html_paths: frozenset[str] = HTML_PATHS,
    ) -> None:
        super().__init__(app)
        self._html_paths = html_paths
        # Precomputed: this is a per-response string that never varies.
        self._hsts = (
            f"max-age={hsts_max_age}; includeSubDomains"
            if hsts and hsts_max_age
            else None
        )

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        headers = response.headers

        headers["Content-Security-Policy"] = (
            HTML_CSP if request.url.path in self._html_paths else API_CSP
        )
        # SAMEORIGIN, not DENY — trap 1 in the module docstring. This is the
        # legacy twin of `frame-ancestors 'self'`, kept for the browsers and
        # scanners that still read it.
        headers["X-Frame-Options"] = "SAMEORIGIN"
        # Assignment, never append: attachments.py sets this too (trap 2).
        headers["X-Content-Type-Options"] = "nosniff"
        headers["Referrer-Policy"] = REFERRER_POLICY
        headers["Permissions-Policy"] = PERMISSIONS_POLICY
        if self._hsts is not None:
            headers["Strict-Transport-Security"] = self._hsts
        return response
