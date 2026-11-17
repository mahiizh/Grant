import pytest
from fastapi.testclient import TestClient


def test_root_endpoint(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert "GraphRAG" in data["name"]


def test_health_liveness(client: TestClient) -> None:
    response = client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_readiness(client: TestClient) -> None:
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "configured_stores" in data
    assert data["configured_stores"]["postgres"] is True
    assert data["configured_stores"]["qdrant"] is True
    assert data["configured_stores"]["neo4j"] is True
    assert data["configured_stores"]["redis"] is True


def test_api_v1_health_prefix(client: TestClient) -> None:
    response = client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_system_health_endpoint(client: TestClient) -> None:
    """System health returns 200 (ok) when all stores are reachable or 503 (degraded)
    when any store is down. The shape must always include all four components."""
    response = client.get("/api/v1/health")
    # 200 (healthy) or 503 (degraded) — both are valid without Docker.
    assert response.status_code in (200, 503)
    data = response.json()
    assert data["status"] in ("ok", "degraded")
    assert "components" in data
    assert "postgres" in data["components"]
    assert "qdrant" in data["components"]
    assert "neo4j" in data["components"]
    assert "redis" in data["components"]


def test_api_v1_system_health_endpoint(client: TestClient) -> None:
    """Alias for the system health check — asserts shape only, not store liveness."""
    response = client.get("/api/v1/health")
    assert response.status_code in (200, 503)
    data = response.json()
    assert data["status"] in ("ok", "degraded")
    assert "components" in data


@pytest.mark.integration
def test_system_health_all_stores_up(client: TestClient) -> None:
    """Requires Docker (postgres:5433, qdrant:6333, neo4j:7687, redis:6379)."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
