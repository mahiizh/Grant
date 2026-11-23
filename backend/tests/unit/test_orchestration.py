from datetime import UTC, datetime
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from app.api.routes.query import set_orchestrator
from app.cache.exact import ExactCache
from app.cache.semantic import SemanticCache
from app.core.acl import ACLScope
from app.domain import Chunk, Entity, Provenance, Relation, TemporalBounds
from app.graph.retrievers import GraphRetriever as RealGraphRetriever
from app.main import app
from app.orchestration.router import QueryRouter
from app.orchestration.workflow import RAGOrchestrator
from app.retrieval.filters import RetrievalFilter
from app.retrieval.hybrid import HybridRetriever as RealHybridRetriever
from tests.fakes.fake_redis import FakeRedis
from tests.fakes.in_memory_retrievers import (
    FakeGraphRetriever as GraphRetriever,
)
from tests.fakes.in_memory_retrievers import (
    FakeHybridRetriever as HybridRetriever,
)


def build_test_orchestrator(cache_enabled: bool = True) -> RAGOrchestrator:
    now = datetime(2026, 3, 1, tzinfo=UTC)
    prov = Provenance.from_document("corpus/rfc_001.md")
    acl = ACLScope.public()

    c1 = Chunk(
        chunk_id="chunk_storage_01",
        doc_id="doc_rfc_001",
        index=0,
        text="PostgreSQL 16 acts as the single source of truth for all documents.",
        tokens=12,
        acl_scope=acl,
        temporal=TemporalBounds(valid_from=now),
        provenance=prov,
    )
    c2 = Chunk(
        chunk_id="chunk_inc_02",
        doc_id="doc_postmortem_04",
        index=0,
        text="Incident INC-2026-04 impacted PaymentGateway with a 24% failure rate.",
        tokens=11,
        acl_scope=acl,
        temporal=TemporalBounds(valid_from=now),
        provenance=prov,
    )

    hybrid = HybridRetriever()
    hybrid.index_chunks([c1, c2])

    # Graph
    e1 = Entity(
        entity_id="ent_bob",
        name="Bob Kumar",
        entity_type="PERSON",
        acl_scope=acl,
        temporal=TemporalBounds.current(),
        provenance=prov,
    )
    e2 = Entity(
        entity_id="ent_elena",
        name="Elena Rostova",
        entity_type="PERSON",
        acl_scope=acl,
        temporal=TemporalBounds.current(),
        provenance=prov,
    )
    rel = Relation(
        relation_id="r1",
        source_entity_id="ent_bob",
        target_entity_id="ent_elena",
        relation_type="COORDINATES_WITH",
        acl_scope=acl,
        temporal=TemporalBounds.current(),
        provenance=prov,
    )

    graph = GraphRetriever()
    graph.index_graph(entities=[e1, e2], relations=[rel], chunks=[c1, c2])

    # Inject FakeRedis so unit tests never require a live Redis server.
    exact_cache = ExactCache(redis_client=cast(Any, FakeRedis())) if cache_enabled else None
    sem_cache = SemanticCache(redis_client=cast(Any, FakeRedis())) if cache_enabled else None

    return RAGOrchestrator(
        hybrid_retriever=cast(RealHybridRetriever, hybrid),
        graph_retriever=cast(RealGraphRetriever, graph),
        exact_cache=exact_cache,
        semantic_cache=sem_cache,
        cache_enabled=cache_enabled,
    )


def test_query_router_classification() -> None:
    # 1. Unanswerable -> abstain
    assert QueryRouter.route("What was the company ARR for fiscal year 2025?") == "abstain"
    assert QueryRouter.route("Which AWS region hosts the cluster?") == "abstain"

    # 2. Multi-hop -> graph
    assert (
        QueryRouter.route(
            "Who leads the team responsible for the database "
            "where outbox events are initially staged?"
        )
        == "graph"
    )

    # 3. Global summary -> hybrid
    assert (
        QueryRouter.route("Summarize the responsibilities across all engineering teams") == "hybrid"
    )

    # 4. Local fact -> vector
    assert QueryRouter.route("Which database acts as the single source of truth?") == "vector"


@pytest.mark.anyio
async def test_orchestrator_vector_fact_execution() -> None:
    orchestrator = build_test_orchestrator()
    orchestrator.exact_cache.clear()
    orchestrator.semantic_cache.clear()

    state = await orchestrator.run(
        query="Which database acts as the single source of truth?",
    )

    assert state["route"] == "vector"
    assert not state["is_cached"]
    assert not state["is_abstention"]
    assert len(state["evidence"]) > 0
    assert "PostgreSQL 16" in state["answer"]
    assert "[chunk_storage_01]" in state["answer"]
    assert state["citations_valid"]
    assert state["cost_usd"] > 0.0
    assert state["latency_ms"] > 0.0
    assert state["retrieval_latency_ms"] > 0.0
    assert state["retrieval_latency_ms"] <= state["latency_ms"]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("config", "method"),
    [
        ("dense", "dense"),
        ("sparse", "sparse"),
        ("hybrid", "hybrid"),
        ("full", "hybrid"),
    ],
)
async def test_orchestrator_retrieval_configs(config: str, method: str) -> None:
    orchestrator = build_test_orchestrator()
    orchestrator.exact_cache.clear()
    orchestrator.semantic_cache.clear()

    state = await orchestrator.run(
        query="Which database acts as the single source of truth?",
        retrieval_config=config,  # type: ignore[arg-type]
    )

    assert state["retrieval_config"] == config
    # The router decision is still recorded, so router accuracy stays comparable.
    assert state["route"] == "vector"
    assert state["evidence"]
    assert {ev.retrieval_method for ev in state["evidence"]} == {method}


class CountingGraphRetriever(GraphRetriever):
    """Fake graph retriever that records every traversal entry."""

    def __init__(self) -> None:
        super().__init__()
        self.search_entities_calls = 0

    def search_entities(
        self,
        query: str,
        top_k: int = 5,
        filter_criteria: RetrievalFilter | None = None,
    ) -> Any:
        self.search_entities_calls += 1
        return super().search_entities(query, top_k=top_k, filter_criteria=filter_criteria)


@pytest.mark.anyio
async def test_graph_forced_enters_graph_branch_on_every_row() -> None:
    orchestrator = build_test_orchestrator(cache_enabled=False)
    graph = CountingGraphRetriever()
    orchestrator.graph_retriever = cast(RealGraphRetriever, graph)

    queries = [
        "Which database acts as the single source of truth?",
        "What was the company ARR for fiscal year 2025?",
        "Who leads the team responsible for the database where outbox events are staged?",
        "Summarize the responsibilities across all engineering teams",
    ]
    for query in queries:
        state = await orchestrator.run(query=query, retrieval_config="graph_forced")
        assert state["retrieval_config"] == "graph_forced"
        assert any(span["name"] == "Graph Traversal: Cypher BFS" for span in state.get("spans", []))

    # Includes a router-abstain row: the router decision is still recorded but
    # does not prevent graph traversal in this config.
    assert graph.search_entities_calls == len(queries)


@pytest.mark.anyio
async def test_orchestrator_abstention_execution() -> None:
    orchestrator = build_test_orchestrator()

    state = await orchestrator.run(
        query="What is the Snowflake data lake encryption algorithm?",
    )

    assert state["route"] == "abstain"
    assert state["is_abstention"]
    assert "sufficient information" in state["answer"]
    assert state["cost_usd"] == 0.0


@pytest.mark.anyio
async def test_orchestrator_cache_hit_execution() -> None:
    orchestrator = build_test_orchestrator()

    # Pre-populate exact cache
    from app.domain import Answer, Evidence

    query = "Warm cache test query"
    ev = Evidence(
        chunk_id="chunk_storage_01",
        doc_id="doc_rfc_001",
        text="Cached answer text",
        score=1.0,
        retrieval_method="hybrid",
        provenance=Provenance.from_document("corpus/rfc_001.md"),
    )
    ans = Answer(query=query, answer="Precomputed cached answer [chunk_storage_01]", evidence=[ev])
    orchestrator.exact_cache.set(query, ans, ACLScope.public())

    state = await orchestrator.run(query=query)

    assert state["is_cached"]
    assert state["answer"] == "Precomputed cached answer [chunk_storage_01]"
    assert state["cost_usd"] == 0.0


@pytest.mark.anyio
async def test_orchestrator_no_cache_never_returns_cached_answer() -> None:
    orchestrator = build_test_orchestrator(cache_enabled=False)
    query = "Which database acts as the single source of truth?"

    first = await orchestrator.run(query=query)
    second = await orchestrator.run(query=query)

    assert orchestrator.cache_enabled is False
    assert not first["is_cached"]
    assert not second["is_cached"]
    assert first["cost_usd"] > 0.0
    assert second["cost_usd"] > 0.0
    assert second["retrieval_latency_ms"] > 0.0


def test_fastapi_query_endpoint() -> None:
    orchestrator = build_test_orchestrator()
    set_orchestrator(orchestrator)

    client = TestClient(app)
    response = client.post(
        "/api/v1/query",
        json={
            "query": "Which database acts as the single source of truth?",
            "tenant_id": "default",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["query"] == "Which database acts as the single source of truth?"
    assert "PostgreSQL 16" in data["answer"]
    assert len(data["evidence"]) > 0
    assert data["cost_usd"] >= 0.0
    assert data["latency_ms"] >= 0.0
