"""Live-store checks for the Step 7 Graph UI API.

Uses only the isolated test stores. Verifies that the graph exposes Document,
Entity and Query nodes (never Chunk nodes), that an entity click resolves
Postgres mentions to ACL-checked Qdrant chunk text, that a query click resolves
to its stored answer/source/path, and that both source-kind and minimum
co-occurrence filters are honored.
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.acl import ACLScope
from app.db.models import EntityMentionRecord, EntityRecord
from app.db.postgres import get_session
from app.history.service import QueryHistoryService
from app.indexing.outbox_worker import OutboxWorker
from app.ingestion.pipeline import IngestionPipeline
from app.main import app

pytestmark = pytest.mark.integration

ALICE = "usr_alice_01"


async def _drain_outbox() -> int:
    worker = OutboxWorker()
    try:
        return await worker.drain()
    finally:
        await worker.qdrant.close()
        await worker.neo4j.close()
        await worker.entity_indexer.close()


@pytest.mark.asyncio
async def test_step7_graph_ui_endpoints_and_filters() -> None:
    suffix = uuid.uuid4().hex[:10]
    content = (
        f"# Step Seven Ledger {suffix}\n\n"
        "Step Seven Beacon syncs PostgreSQL and Qdrant. "
        "Aurora Key protects the Data Platform Team gateway in Qdrant.\n\n"
        "The Step Seven Beacon and Aurora Key appear again with PostgreSQL and Qdrant."
    )
    async with get_session() as session:
        summary = await IngestionPipeline.ingest_text(
            session=session,
            content=content,
            source_uri=f"step7://graph-ui/{suffix}.md",
            owner_user_id=ALICE,
            use_gliner=False,
        )
        await session.commit()
    doc_id = summary.doc_id
    assert summary.chunk_count >= 1
    assert await _drain_outbox() > 0

    async with get_session() as session:
        entity_rows = (
            await session.execute(
                select(EntityMentionRecord.entity_id, EntityRecord.canonical_name)
                .join(EntityRecord, EntityRecord.entity_id == EntityMentionRecord.entity_id)
                .where(
                    EntityMentionRecord.doc_id == doc_id,
                    EntityMentionRecord.chunk_id.is_not(None),
                )
                .distinct()
            )
        ).all()
    assert entity_rows, "Expected at least one entity mention for the ingested doc"
    entity_id = str(entity_rows[0][0])

    question = f"What protects the Step Seven gateway {suffix}?"
    answer = "Aurora Key protects the Step Seven gateway."
    async with get_session() as session:
        query_id, _ = await QueryHistoryService().record(
            session=session,
            raw_query=question,
            rewritten_query=question,
            answer=answer,
            evidence=[],
            source_kind="docs",
            web_sources=[],
            answer_policy="grounded_plus_web",
            acl_scope=ACLScope.owner(ALICE),
            owner_user_id=ALICE,
            thread_id=None,
            source="docs",
            answer_path=["docs"],
            top_score=0.87,
            stage_timings_ms={"llm": 12.0},
        )
        await session.commit()
    assert await _drain_outbox() > 0

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        alice = {"X-Dev-User": "alice"}
        bob = {"X-Dev-User": "bob"}

        resp = await client.get("/api/v1/graph", params={"limit": 1000}, headers=alice)
        assert resp.status_code == 200
        body = resp.json()
        node_kinds = {node["node_kind"] for node in body["nodes"]}
        assert {"document", "entity", "query"} <= node_kinds
        assert node_kinds <= {"document", "entity", "query"}
        assert all(node["type"] != "chunk" for node in body["nodes"])
        assert doc_id in {node["id"] for node in body["nodes"] if node["node_kind"] == "document"}
        assert query_id in {node["id"] for node in body["nodes"] if node["node_kind"] == "query"}
        assert any(link["label"] == "MENTIONS" for link in body["links"])

        # Source kind "document" must hide chat-origin Query nodes.
        docs = await client.get(
            "/api/v1/graph",
            params={"limit": 1000, "source_kind": "document"},
            headers=alice,
        )
        assert docs.status_code == 200
        assert all(node["node_kind"] != "query" for node in docs.json()["nodes"])

        # Minimum co-occurrence applies to aggregated MENTIONS/CO_OCCURS counts.
        strict = await client.get(
            "/api/v1/graph",
            params={"limit": 1000, "min_cooccurrence": 999},
            headers=alice,
        )
        assert strict.status_code == 200
        assert strict.json()["links"] == []

        neighbors = await client.get(
            f"/api/v1/graph/nodes/{entity_id}/neighbors",
            headers=alice,
        )
        assert neighbors.status_code == 200
        assert any(node["id"] == doc_id for node in neighbors.json()["nodes"])

        chunks_resp = await client.get(
            f"/api/v1/graph/entities/{entity_id}/chunks",
            headers=alice,
        )
        assert chunks_resp.status_code == 200
        chunks = chunks_resp.json()["chunks"]
        assert chunks and all(chunk["text"] for chunk in chunks)
        assert all(chunk["chunk_id"] for chunk in chunks)
        assert any(chunk["doc_id"] == doc_id for chunk in chunks)

        detail = await client.get(f"/api/v1/graph/queries/{query_id}", headers=alice)
        assert detail.status_code == 200
        detail_body = detail.json()
        assert detail_body["query"] == question
        assert detail_body["answer"] == answer
        assert detail_body["source"] == "docs"
        assert detail_body["path"] == ["docs"]
        assert detail_body["top_score"] == 0.87

        # Bob must not receive Alice's chunk text or answer.
        bob_chunks = await client.get(
            f"/api/v1/graph/entities/{entity_id}/chunks",
            headers=bob,
        )
        assert bob_chunks.status_code == 200
        assert bob_chunks.json()["chunks"] == []
        bob_detail = await client.get(f"/api/v1/graph/queries/{query_id}", headers=bob)
        assert bob_detail.status_code == 404
