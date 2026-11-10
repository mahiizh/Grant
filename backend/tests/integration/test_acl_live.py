"""Live-container ACL leak tests for Qdrant pushdown, Neo4j Cypher, and HTTP surfaces.

These require the Docker Compose stack and an ingested dev corpus:
``make up && make ingest``. They are marked ``integration`` and are skipped only
when the caller deselects that marker.
"""

from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.auth import AuthenticatedUser
from app.core.config import get_settings
from app.graph.retrievers import GraphRetriever
from app.main import app
from app.retrieval.dense import DenseRetriever
from app.retrieval.filters import RetrievalFilter
from app.retrieval.reranker import get_reranker
from app.retrieval.sparse import BM25Retriever

DATA_PLATFORM_DOCS = {
    "doc_team_directory_2026",
    "doc_rfc_001",
    "doc_rfc_004",
    "doc_dual_write_consistency",
}
QUERY = "Data Platform Team PostgreSQL outbox ownership"


class _FakeReranker:
    """Constant scorer so the compare endpoint exercises ACL plumbing, not the model."""

    def predict_pairs(self, pairs: list[tuple[str, str]]) -> list[float]:
        return [1.0 for _ in pairs]


def _filter(username: str, scope: str | None = None) -> RetrievalFilter:
    user = AuthenticatedUser(username, get_settings().DEV_USERS[username])
    return user.to_retrieval_filter(scope)


def _assert_no_data_platform(doc_ids: set[str]) -> None:
    leaked = doc_ids & DATA_PLATFORM_DOCS
    assert not leaked, f"ACL leak: bob retrieved data-platform docs {sorted(leaked)}"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_qdrant_payload_filter_does_not_leak() -> None:
    """Real Qdrant dense and sparse search must prune data-platform chunks for bob."""
    dense = DenseRetriever()
    sparse = BM25Retriever()
    bob = _filter("bob")
    alice = _filter("alice")

    for retriever in (dense, sparse):
        bob_docs = {
            payload["doc_id"]
            for _, _, payload in await retriever.search(QUERY, top_k=45, filter_criteria=bob)
        }
        _assert_no_data_platform(bob_docs)

        alice_docs = {
            payload["doc_id"]
            for _, _, payload in await retriever.search(QUERY, top_k=45, filter_criteria=alice)
        }
        # Non-vacuity: alice's filter really does admit the data-platform docs.
        assert alice_docs & DATA_PLATFORM_DOCS


@pytest.mark.integration
@pytest.mark.asyncio
async def test_neo4j_cypher_acl_does_not_leak() -> None:
    """Real Cypher predicates must hide data-platform entities and paths from bob."""
    graph = GraphRetriever()
    try:
        bob = _filter("bob")
        alice = _filter("alice")

        bob_entities = await graph.search_entities("Data Platform", filter_criteria=bob)
        assert bob_entities == []

        alice_entities = await graph.search_entities("Data Platform", filter_criteria=alice)
        assert any(entity["name"] == "Data Platform Team" for entity in alice_entities)

        # Bob cannot even start a path from a data-platform entity.
        assert await graph.find_path("Bob Kumar", "INC-2026-04", filter_criteria=bob) is None
        assert (
            await graph.find_path("Alice Chen", "Data Platform Team", filter_criteria=bob) is None
        )

        alice_path = await graph.find_path(
            "Alice Chen", "Data Platform Team", filter_criteria=alice
        )
        assert alice_path is not None

        # Evidence for an sre-visible entity must only contain sre/public chunks.
        bob_evidence = await graph.retrieve_path_evidence(["INC-2026-04"], filter_criteria=bob)
        assert bob_evidence
        _assert_no_data_platform({item.doc_id for item in bob_evidence})
    finally:
        await graph.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_retrieval_compare_endpoint_does_not_leak() -> None:
    """`/retrieval/compare` must apply the same ACL to dense, sparse, and fused results."""
    app.dependency_overrides[get_reranker] = _FakeReranker
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            bob_resp = await client.get(
                "/api/v1/retrieval/compare",
                params={"query": QUERY, "scope": "sre"},
                headers={"X-Dev-User": "bob"},
            )
            assert bob_resp.status_code == 200
            bob_docs = {c["doc_title"] for c in bob_resp.json()["candidates"]}
            _assert_no_data_platform(bob_docs)

            alice_resp = await client.get(
                "/api/v1/retrieval/compare",
                params={"query": QUERY, "scope": "data-platform"},
                headers={"X-Dev-User": "alice"},
            )
            assert alice_resp.status_code == 200
            alice_docs = {c["doc_title"] for c in alice_resp.json()["candidates"]}
            assert alice_docs & DATA_PLATFORM_DOCS
    finally:
        app.dependency_overrides.pop(get_reranker, None)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_graph_endpoints_do_not_leak() -> None:
    """`/graph` and `/graph/path` must not expose data-platform nodes or paths to bob."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        bob_resp = await client.get(
            "/api/v1/graph", params={"scope": "sre"}, headers={"X-Dev-User": "bob"}
        )
        assert bob_resp.status_code == 200
        bob_nodes: list[dict[str, Any]] = bob_resp.json()["nodes"]
        bob_names = {node["name"] for node in bob_nodes}
        assert bob_names & {"Alice Chen", "Data Platform Team", "PostgreSQL"} == set()
        # Non-vacuity: bob still sees his own sre subgraph.
        assert "INC-2026-04" in bob_names

        alice_resp = await client.get(
            "/api/v1/graph", params={"scope": "data-platform"}, headers={"X-Dev-User": "alice"}
        )
        assert alice_resp.status_code == 200
        alice_names = {node["name"] for node in alice_resp.json()["nodes"]}
        assert "Data Platform Team" in alice_names

        bob_path = await client.get(
            "/api/v1/graph/path",
            params={"from": "Alice Chen", "to": "Data Platform Team", "scope": "sre"},
            headers={"X-Dev-User": "bob"},
        )
        assert bob_path.status_code == 200
        assert bob_path.json()["found"] is False

        alice_path = await client.get(
            "/api/v1/graph/path",
            params={
                "from": "Alice Chen",
                "to": "Data Platform Team",
                "scope": "data-platform",
            },
            headers={"X-Dev-User": "alice"},
        )
        assert alice_path.status_code == 200
        assert alice_path.json()["found"] is True
