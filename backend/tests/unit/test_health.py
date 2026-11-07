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
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "components" in data
    assert "postgres" in data["components"]
    assert "qdrant" in data["components"]
    assert "neo4j" in data["components"]
    assert "redis" in data["components"]


def test_api_v1_system_health_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "components" in data
