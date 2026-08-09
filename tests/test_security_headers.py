"""Stage D closeout: the security-header layer (api-standards §10).

Before this, the app set no security headers at all and no test asserted a
middleware-set response header — so this module is the first of both. The
regression that matters most does NOT live here: it is in
``test_reimb_packet_api.py``, on the real PDF response the SPA frames, because
that is where a wrong ``frame-ancestors`` would actually bite.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from office_connect.core.api.security_headers import (
    API_CSP,
    HTML_CSP,
    SecurityHeadersMiddleware,
)
from office_connect.core.config import Settings

ALWAYS = (
    "Content-Security-Policy",
    "X-Frame-Options",
    "X-Content-Type-Options",
    "Referrer-Policy",
    "Permissions-Policy",
)


# --- the real app -----------------------------------------------------------


async def test_every_header_is_present_on_an_ordinary_response(client):
    r = await client.get("/health")
    assert r.status_code == 200
    for header in ALWAYS:
        assert header in r.headers, f"{header} missing"
    assert r.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


async def test_json_surfaces_get_the_locked_down_policy(client):
    r = await client.get("/api/v1/config")
    assert r.status_code == 200
    assert r.headers["Content-Security-Policy"] == API_CSP
    # The whole point of the API policy: a JSON response should be able to load
    # nothing, frame nothing and submit nowhere.
    assert "default-src 'none'" in r.headers["Content-Security-Policy"]


async def test_frame_ancestors_is_self_not_none(client):
    """⚠ The trap, pinned. `frame-ancestors 'none'` and `X-Frame-Options: DENY`
    both look like the safer answer and both blank the claim-packet preview:
    `PacketPreview.tsx` embeds a PDF this app serves from this origin."""
    csp = (await client.get("/api/v1/config")).headers["Content-Security-Policy"]
    assert "frame-ancestors 'self'" in csp
    assert "frame-ancestors 'none'" not in csp


@pytest.mark.parametrize("path", ["/docs", "/redoc"])
async def test_the_api_docs_get_the_html_policy_and_still_render(client, path):
    """Swagger UI and ReDoc boot from an INLINE script and fetch assets from
    jsDelivr. Under the API policy they would render a blank page — and no test
    would have noticed, because nothing else in the suite opens them."""
    r = await client.get(path)
    assert r.status_code == 200
    assert r.headers["Content-Security-Policy"] == HTML_CSP
    assert "'unsafe-inline'" in r.headers["Content-Security-Policy"]
    assert "cdn.jsdelivr.net" in r.headers["Content-Security-Policy"]
    # The inline <script> the policy exists for is really there.
    assert "<script" in r.text


async def test_the_audit_report_gets_the_html_policy(client):
    """`GET /api/v1/audit/verify` renders an inline <style> block. It is behind
    `audit.verify`, and the 401 is exactly what makes this a two-in-one check:
    the policy is chosen by PATH, so it is correct before authorization runs."""
    r = await client.get("/api/v1/audit/verify")
    assert r.status_code == 401
    assert r.headers["Content-Security-Policy"] == HTML_CSP


async def test_headers_survive_the_error_paths(client):
    """A CSRF rejection and a 404 are produced inside the middleware stack. The
    layer sits outside CSRF so both carry the headers — a header present only on
    2xx is one a scanner passes and an attacker walks around."""
    csrf = await client.post(
        "/api/v1/auth/login", json={"identifier": "a", "password": "b"}
    )
    assert csrf.status_code == 403 and csrf.json()["error"]["code"] == "csrf_failed"

    missing = await client.get("/api/v1/no-such-route")
    assert missing.status_code == 404

    for r in (csrf, missing):
        for header in ALWAYS:
            assert header in r.headers, f"{header} missing on {r.status_code}"


async def test_hsts_is_absent_in_local_dev(client):
    """The suite runs at APP_ENV=local. HSTS is the one header that breaks plain
    http for a whole year per host, and localhost is shared with every other
    project on this machine — so `local` must never emit it."""
    assert "Strict-Transport-Security" not in (await client.get("/health")).headers


# --- the production shape ---------------------------------------------------
#
# `get_settings` is lru_cached and main.py resolves it once at import, so no env
# var can move the running app's HSTS flag. The middleware takes kwargs for
# exactly this reason: the production shape is a real assertion, not a comment.


async def _headers_from(**kwargs) -> dict:
    app = Starlette(routes=[Route("/x", lambda request: PlainTextResponse("ok"))])
    app.add_middleware(SecurityHeadersMiddleware, **kwargs)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        return dict((await c.get("/x")).headers)


async def test_hsts_is_emitted_when_enabled():
    headers = await _headers_from(hsts=True, hsts_max_age=31536000)
    assert headers["strict-transport-security"] == (
        "max-age=31536000; includeSubDomains"
    )


async def test_hsts_is_omitted_when_disabled():
    assert "strict-transport-security" not in await _headers_from(
        hsts=False, hsts_max_age=31536000
    )


def test_hsts_resolves_from_app_env_like_the_cookie_flag():
    """Both settings answer one question — *is this deployment https?* — so they
    must never disagree. An explicit value still wins over the environment."""
    for env in ("local", "staging", "production"):
        s = Settings(app_env=env)
        assert s.resolved_hsts_enabled == s.resolved_cookie_secure
    assert Settings(app_env="local").resolved_hsts_enabled is False
    assert Settings(app_env="production").resolved_hsts_enabled is True
    forced_off = Settings(app_env="production", hsts_enabled=False)
    assert forced_off.resolved_hsts_enabled is False
    assert Settings(app_env="local", hsts_enabled=True).resolved_hsts_enabled is True
