import pytest
from httpx import ASGITransport, AsyncClient

from app.indexing.reconciler import run_reconciliation
from app.main import app


@pytest.mark.integration
@pytest.mark.asyncio
async def test_acl_leak_protection() -> None:
    """Verify that a caller cannot request another identity's shared scope."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        forbidden = await client.post(
            "/api/v1/query",
            headers={"X-Dev-User": "alice"},
            json={"query": "Summarize private audit material", "scope": "shared-audit"},
        )
        assert forbidden.status_code == 403
        assert "not authorized for shared scope 'shared-audit'" in forbidden.json()["detail"]

        allowed = await client.post(
            "/api/v1/query",
            headers={"X-Dev-User": "auditor"},
            json={"query": "Summarize private audit material", "scope": "shared-audit"},
        )
        assert allowed.status_code == 200


@pytest.mark.integration
@pytest.mark.asyncio
async def test_small_talk_skips_retrieval() -> None:
    """Verify that greetings trigger small_talk route with zero evidence and cost."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/query",
            headers={"X-Dev-User": "alice"},
            json={"query": "Hello!"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["strategy_used"] == "small_talk"
        assert len(data["evidence"]) == 0
        assert data["cost_usd"] == 0.0
        assert "Hello!" in data["answer"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_health_check_stores() -> None:
    """Verify health endpoint queries real Postgres, Qdrant, Neo4j, Redis and returns 200."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        components = data["components"]
        assert components["postgres"]["status"] == "healthy"
        assert components["qdrant"]["status"] == "healthy"
        assert components["neo4j"]["status"] == "healthy"
        assert components["redis"]["status"] == "healthy"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_reconciler_zero_drift() -> None:
    """Verify reconciler confirms 100% synchronization across Postgres, Qdrant, Neo4j."""
    exit_code = await run_reconciliation(repair=False)
    assert exit_code == 0
