from datetime import UTC, datetime
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from app.api.routes.query import get_orchestrator, set_orchestrator
from app.cache.exact import ExactCache
from app.core.acl import ACLScope
from app.domain import Chunk, Entity, Provenance, Relation
from app.graph.retrievers import GraphRetriever as RealGraphRetriever
from app.llm.gateway import ModelResponse
from app.main import app
from app.orchestration.workflow import RAGOrchestrator, classify_route
from app.retrieval.filters import RetrievalFilter
from app.retrieval.hybrid import HybridRetriever as RealHybridRetriever
from tests.fakes.fake_gateway import FakeModelGateway
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
        ingested_at=now,
        provenance=prov,
    )
    c2 = Chunk(
        chunk_id="chunk_inc_02",
        doc_id="doc_postmortem_04",
        index=0,
        text="Incident INC-2026-04 impacted PaymentGateway with a 24% failure rate.",
        tokens=11,
        acl_scope=acl,
        ingested_at=now,
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
        ingested_at=now,
        provenance=prov,
    )
    e2 = Entity(
        entity_id="ent_elena",
        name="Elena Rostova",
        entity_type="PERSON",
        acl_scope=acl,
        ingested_at=now,
        provenance=prov,
    )
    rel = Relation(
        relation_id="r1",
        source_entity_id="ent_bob",
        target_entity_id="ent_elena",
        relation_type="COORDINATES_WITH",
        acl_scope=acl,
        ingested_at=now,
        provenance=prov,
    )

    graph = GraphRetriever()
    graph.index_graph(entities=[e1, e2], relations=[rel], chunks=[c1, c2])

    # Inject FakeRedis so unit tests never require a live Redis server.
    exact_cache = ExactCache(redis_client=cast(Any, FakeRedis())) if cache_enabled else None

    return RAGOrchestrator(
        hybrid_retriever=cast(RealHybridRetriever, hybrid),
        graph_retriever=cast(RealGraphRetriever, graph),
        exact_cache=exact_cache,
        cache_enabled=cache_enabled,
    )


def test_inline_route_classification() -> None:
    # 1. Unanswerable -> abstain in grounded_only
    assert classify_route("What was the company ARR for fiscal year 2025?") == "abstain"
    assert classify_route("Which AWS region hosts the cluster?") == "abstain"

    # 2. Generic multi-hop -> graph (no corpus/team-specific keywords)
    assert (
        classify_route("What is the upstream dependency chain for the payment service?")
        == "graph"
    )

    # 3. Global summary -> hybrid
    assert (
        classify_route("Summarize the responsibilities across all engineering teams") == "hybrid"
    )

    # 4. Local fact -> vector
    assert classify_route("Which database acts as the single source of truth?") == "vector"


@pytest.mark.anyio
async def test_orchestrator_vector_fact_execution() -> None:
    orchestrator = build_test_orchestrator()
    orchestrator.exact_cache.clear()

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


class RewriteGateway(FakeModelGateway):
    """Fake gateway whose only model response is a multi-turn rewrite."""

    async def complete(
        self,
        prompt: str,
        system_prompt: str | None = None,
        model: str | None = None,
        max_tokens: int = 800,
        temperature: float = 0.1,
        mock_response: str | None = None,
    ) -> ModelResponse:
        return await super().complete(
            prompt=prompt,
            system_prompt=system_prompt,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            mock_response="What is OutboxWorker's p99 latency SLA?",
        )


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
async def test_retrieval_only_skips_answer_generation() -> None:
    orchestrator = build_test_orchestrator(cache_enabled=False)
    gateway = FakeModelGateway()
    orchestrator.gateway = cast(Any, gateway)

    state = await orchestrator.run(
        query="Which database acts as the single source of truth?",
        retrieval_only=True,
    )

    assert gateway.total_calls == 0
    assert state["evidence"]
    assert state["answer"] == ""
    assert any(
        span["name"] == "Retrieval Only: skip answer generation" for span in state.get("spans", [])
    )


@pytest.mark.anyio
async def test_retrieval_only_still_rewrites_multi_turn_queries() -> None:
    orchestrator = build_test_orchestrator(cache_enabled=False)
    gateway = RewriteGateway()
    gateway.default_model = "rewrite-model"
    orchestrator.gateway = cast(Any, gateway)

    state = await orchestrator.run(
        query="What is its p99 latency SLA?",
        thread_history=[
            {"role": "user", "content": "What is the SLA for OutboxWorker?"},
            {"role": "assistant", "content": "OutboxWorker targets 47ms."},
        ],
        retrieval_only=True,
    )

    assert "OutboxWorker" in state["rewritten_query"]
    # One model call is the multi-turn rewrite; no generation call follows it.
    # Zero evidence here legitimately reaches the abstention node instead.
    assert gateway.total_calls == 1


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
    previous_orchestrator = get_orchestrator()
    orchestrator = build_test_orchestrator()
    set_orchestrator(orchestrator)

    try:
        client = TestClient(app)
        response = client.post(
            "/api/v1/query",
            json={
                "query": "Which database acts as the single source of truth?",
            },
        )
    finally:
        set_orchestrator(previous_orchestrator)

    assert response.status_code == 200
    data = response.json()
    assert data["query"] == "Which database acts as the single source of truth?"
    assert "PostgreSQL 16" in data["answer"]
    assert len(data["evidence"]) > 0
    assert data["cost_usd"] >= 0.0
    assert data["latency_ms"] >= 0.0
