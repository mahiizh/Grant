import pytest
from httpx import ASGITransport, AsyncClient

from app.indexing.reconciler import run_reconciliation
from app.main import app


@pytest.mark.integration
@pytest.mark.asyncio
async def test_acl_leak_protection() -> None:
    """Verify that a user without executive-audit access cannot retrieve restricted chunks or citations."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. User Alice (scopes: data-platform, public) tries to request executive-audit scope explicitly -> 403
        resp_forbidden = await client.post(
            "/api/v1/query",
            headers={"X-Dev-User": "alice"},
            json={
                "query": "What is the capital reserve ratio in the executive audit?",
                "scope": "executive-audit",
            },
        )
        assert resp_forbidden.status_code == 403
        assert "not authorized for scope 'executive-audit'" in resp_forbidden.json()["detail"]

        # 2. User Alice queries without scope parameter -> must receive ZERO chunks/citations from executive-audit
        resp_leak_check = await client.post(
            "/api/v1/query",
            headers={"X-Dev-User": "alice"},
            json={"query": "What were the findings in the board audit and Project Obsidian?"},
        )
        assert resp_leak_check.status_code == 200
        data = resp_leak_check.json()
        citations = data.get("evidence", [])
        for cit in citations:
            assert cit["doc_id"] != "doc_board_audit_q1_2026", (
                "ACL LEAK: Executive audit chunk was retrieved!"
            )
            assert "doc_board_audit" not in cit["chunk_id"], (
                "ACL LEAK: Executive audit chunk returned!"
            )

        # 3. Auditor user (scopes: executive-audit, public) requests executive-audit scope -> allowed
        resp_auditor = await client.post(
            "/api/v1/query",
            headers={"X-Dev-User": "auditor"},
            json={
                "query": "What is the capital reserve ratio in the executive audit report?",
                "scope": "executive-audit",
            },
        )
        assert resp_auditor.status_code == 200
        auditor_data = resp_auditor.json()
        assert len(auditor_data.get("evidence", [])) > 0
        assert any(c["doc_id"] == "doc_board_audit_q1_2026" for c in auditor_data["evidence"])


@pytest.mark.integration
@pytest.mark.asyncio
async def test_temporal_as_of_filtering() -> None:
    """Verify bi-temporal retrieval: SLA v1 (50ms) as of Jan 2026 vs SLA v2 (25ms) as of April 2026."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # As of 2026-02-01: SLA v1 is effective (p99 = 50ms)
        resp_v1 = await client.post(
            "/api/v1/query",
            headers={"X-Dev-User": "elena"},
            json={
                "query": "What is the p99 latency SLA for payment authorization?",
                "scope": "payments",
                "as_of": "2026-02-01T00:00:00Z",
            },
        )
        assert resp_v1.status_code == 200
        v1_data = resp_v1.json()
        assert any(c["doc_id"] == "doc_sla_payments_v1" for c in v1_data["evidence"])
        assert all(c["doc_id"] != "doc_sla_payments_v2" for c in v1_data["evidence"])

        # As of 2026-04-01: SLA v2 is effective (p99 = 25ms)
        resp_v2 = await client.post(
            "/api/v1/query",
            headers={"X-Dev-User": "elena"},
            json={
                "query": "What is the p99 latency SLA for payment authorization?",
                "scope": "payments",
                "as_of": "2026-04-01T00:00:00Z",
            },
        )
        assert resp_v2.status_code == 200
        v2_data = resp_v2.json()
        assert any(c["doc_id"] == "doc_sla_payments_v2" for c in v2_data["evidence"])


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
