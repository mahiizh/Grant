from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.api.routes.query import set_orchestrator
from app.core.acl import ACLScope
from app.domain import Chunk, Entity, Provenance, Relation, TemporalBounds
from app.main import app
from app.orchestration.router import QueryRouter
from app.orchestration.workflow import RAGOrchestrator
from tests.fakes.in_memory_retrievers import (
    FakeGraphRetriever as GraphRetriever,
    FakeHybridRetriever as HybridRetriever,
)


def build_test_orchestrator() -> RAGOrchestrator:
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

    return RAGOrchestrator(
        hybrid_retriever=hybrid,
        graph_retriever=graph,
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
