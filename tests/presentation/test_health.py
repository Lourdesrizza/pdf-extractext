from app.api.v1 import health_router


def test_health_returns_ok_when_mongo_responds(client, monkeypatch):
    async def mongo_available() -> bool:
        return True

    monkeypatch.setattr(health_router, "_ping_mongo", mongo_available)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "connected"}


def test_health_returns_degraded_when_mongo_is_unavailable(client, monkeypatch):
    async def mongo_unavailable() -> bool:
        return False

    monkeypatch.setattr(health_router, "_ping_mongo", mongo_unavailable)

    response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "db": "disconnected"}
