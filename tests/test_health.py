"""Regression from the session-1 scaffold: /health checks both dependencies."""


async def test_health_ok(client):
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["checks"] == {"postgres": "ok", "redis": "ok"}


async def test_root_lists_surfaces(client):
    body = (await client.get("/")).json()
    assert body["health"] == "/health"
    assert body["config"] == "/api/v1/config"
