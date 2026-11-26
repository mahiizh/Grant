"""Live-store checks for Step 4 Neo4j slimming.

Verifies the slim graph shape, Qdrant-owned chunk text, Postgres-owned chunk
links, zero reconciler drift, dry-run purity, graph retrieval parity and ACL
isolation against the isolated test stores only.
"""

import uuid
from typing import Any
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from app.core.acl import ACLScope
from app.db.models import (
    ChunkRecord,
    DocumentRecord,
    EntityMentionRecord,
    EntityRecord,
    OutboxEventRecord,
)
from app.db.postgres import DocumentRepository, get_session
from app.graph.retrievers import GraphRetriever
from app.indexing.neo4j_indexer import Neo4jIndexer
from app.indexing.outbox_worker import OutboxWorker
from app.indexing.qdrant_indexer import EntityVectorIndex, QdrantIndexer
from app.indexing.reconciler import run_reconciliation
from app.ingestion.pipeline import IngestionPipeline
from app.retrieval.filters import RetrievalFilter
from app.web_grounding.web import WebPage
from app.web_grounding.web_ingest import WebPageIngestor

pytestmark = pytest.mark.integration

ALLOWED_NODE_LABELS = {"Document", "Entity", "Query", "Answer", "Message"}
ALLOWED_EDGE_TYPES = {
    "MENTIONS",
    "CO_OCCURS",
    "VERSION_OF",
    "ABOUT",
    "ANSWERED_BY",
    "CITES",
    "NEXT",
}


async def _drain_outbox() -> int:
    worker = OutboxWorker()
    try:
        return await worker.drain()
    finally:
        await worker.qdrant.close()
        await worker.neo4j.close()
        await worker.entity_indexer.close()


async def _neo4j_counts(indexer: Neo4jIndexer) -> dict[str, int]:
    nodes = await indexer.count_nodes()
    edges = await indexer.count_edges()
    async with indexer.driver.session(database=indexer.database) as session:
        label_res = await session.run(
            "MATCH (n) RETURN labels(n) AS labels, count(n) AS cnt"
        )
        label_rows = await label_res.data()
        edge_res = await session.run(
            "MATCH ()-[r]->() RETURN type(r) AS type, count(r) AS cnt"
        )
        edge_rows = await edge_res.data()
    labels = {label for row in label_rows for label in row["labels"]}
    edge_types = {str(row["type"]) for row in edge_rows}
    assert not labels - ALLOWED_NODE_LABELS, f"Unexpected Neo4j labels: {labels}"
    assert not edge_types - ALLOWED_EDGE_TYPES, f"Unexpected Neo4j edges: {edge_types}"
    return {"nodes": nodes, "edges": edges}


async def _outbox_counts() -> dict[str, int]:
    async with get_session() as session:
        rows = (
            await session.execute(
                select(OutboxEventRecord.status, func.count())
                .group_by(OutboxEventRecord.status)
            )
        ).all()
    return {str(status): int(count) for status, count in rows}


async def _snapshot() -> dict[str, Any]:
    async with get_session() as session:
        docs = await session.scalar(select(func.count()).select_from(DocumentRecord))
        chunks = await session.scalar(select(func.count()).select_from(ChunkRecord))
        mentions = await session.scalar(
            select(func.count()).select_from(EntityMentionRecord)
        )
        entities = await session.scalar(select(func.count()).select_from(EntityRecord))

    qdrant = QdrantIndexer()
    entity_index = EntityVectorIndex()
    neo4j = Neo4jIndexer()
    try:
        qdrant_chunks = len(await qdrant.get_all_chunk_ids())
        qdrant_entities = len(await entity_index.get_all_entity_ids())
        neo_counts = await _neo4j_counts(neo4j)
        documents = len(await neo4j.get_all_document_ids())
    finally:
        await qdrant.close()
        await entity_index.close()
        await neo4j.close()

    return {
        "postgres": {
            "documents": int(docs or 0),
            "chunks": int(chunks or 0),
            "mentions": int(mentions or 0),
            "entities": int(entities or 0),
        },
        "qdrant": {"chunks": qdrant_chunks, "entities": qdrant_entities},
        "neo4j": {**neo_counts, "documents": documents},
        "outbox": await _outbox_counts(),
    }


@pytest.mark.asyncio
async def test_step4_slim_graph_and_zero_drift() -> None:
    suffix = uuid.uuid4().hex[:10]
    owner = f"usr_step4_{suffix}"
    source_uri = f"step4://gateway/{suffix}.md"
    bob = f"usr_step4_bob_{suffix}"
    owner_filter = RetrievalFilter(
        acl_scope=ACLScope.owner(owner), owner_user_id=owner
    )
    bob_filter = RetrievalFilter(acl_scope=ACLScope.owner(bob), owner_user_id=bob)

    neo4j = Neo4jIndexer()
    qdrant = QdrantIndexer()
    graph = GraphRetriever()
    try:
        before_counts = await _neo4j_counts(neo4j)
        print(f"Step4 Neo4j counts before ingest: {before_counts}")

        content = (
            "# Step Four Gateway\n\n"
            "Step Four Beacon uses Qdrant and PostgreSQL 16. "
            "Aurora Key protects the Data Platform Team gateway in Qdrant."
        )
        async with get_session() as session:
            summary = await IngestionPipeline.ingest_text(
                session=session,
                content=content,
                source_uri=source_uri,
                owner_user_id=owner,
                use_gliner=False,
            )
            await session.commit()
        doc_id = summary.doc_id
        assert summary.chunk_count == 1
        await _drain_outbox()

        after_ingest_counts = await _neo4j_counts(neo4j)
        print(f"Step4 Neo4j counts after ingest: {after_ingest_counts}")
        assert after_ingest_counts["nodes"] > before_counts["nodes"]
        assert await run_reconciliation(repair=False) == 0

        async with get_session() as session:
            entity_rows = (
                await session.execute(
                    select(
                        EntityMentionRecord.entity_id,
                        EntityRecord.canonical_name,
                    )
                    .join(
                        EntityRecord,
                        EntityRecord.entity_id == EntityMentionRecord.entity_id,
                    )
                    .where(
                        EntityMentionRecord.doc_id == doc_id,
                        EntityMentionRecord.source_kind == "document",
                    )
                    .distinct()
                )
            ).all()
        entity_names = {str(row[1]): str(row[0]) for row in entity_rows}
        assert len(entity_names) >= 2, f"Expected two entities, got {entity_names}"
        path_names = list(entity_names)[:2]
        path = await graph.find_path(
            path_names[0],
            path_names[1],
            filter_criteria=owner_filter,
        )
        assert path is not None, f"No graph path between {path_names}"

        evidence = await graph.retrieve_path_evidence(
            path, top_k=5, filter_criteria=owner_filter
        )
        async with get_session() as session:
            expected_chunk_ids = set(
                (
                    await session.execute(
                        select(EntityMentionRecord.chunk_id)
                        .where(
                            EntityMentionRecord.doc_id == doc_id,
                            EntityMentionRecord.entity_id.in_(entity_names.values()),
                            EntityMentionRecord.chunk_id.is_not(None),
                        )
                        .distinct()
                    )
                ).scalars().all()
            )
        assert expected_chunk_ids
        assert {item.chunk_id for item in evidence} == expected_chunk_ids
        assert all(item.text for item in evidence)
        assert all(item.path == path for item in evidence)

        payloads = await qdrant.get_chunks(sorted(expected_chunk_ids))
        assert set(payloads) == expected_chunk_ids
        for payload in payloads.values():
            for key in (
                "chunk_id",
                "doc_id",
                "owner_user_id",
                "source_kind",
                "title",
                "url",
                "doc_checksum",
                "text",
            ):
                assert key in payload, f"Qdrant payload is missing {key}"
            assert payload["doc_id"] == doc_id
            assert payload["owner_user_id"] == owner

        # The same graph path must be invisible to a different owner.
        bob_evidence = await graph.retrieve_path_evidence(
            path, top_k=5, filter_criteria=bob_filter
        )
        assert bob_evidence == []

        # Web write-back follows the same slim index path as uploads.
        page = WebPage(
            url=f"https://example.test/step4/{suffix}",
            title="Step Four Web Note",
            text="Harbor Lantern guides Meridian Buoy through the channel.",
            fetched_at=datetime.now(UTC).isoformat(),
            provider="test",
        )
        web_evidence = await WebPageIngestor().ingest([page], owner_user_id=owner)
        assert web_evidence
        web_doc_id = web_evidence[0].doc_id
        await _drain_outbox()
        assert await run_reconciliation(repair=False) == 0

        snapshot_before_dry_run = await _snapshot()
        assert await run_reconciliation(dry_run=True) == 0
        assert await _snapshot() == snapshot_before_dry_run

        # Delete the uploaded document: Document node, CO_OCCURS edges, Qdrant
        # points, Postgres mentions and orphan entities all disappear.
        async with get_session() as session:
            deleted = await DocumentRepository.delete_document(session, doc_id)
            await session.commit()
        assert deleted
        await _drain_outbox()

        async with get_session() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(DocumentRecord)
                    .where(DocumentRecord.doc_id == doc_id)
                )
            ) == 0
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(ChunkRecord)
                    .where(ChunkRecord.doc_id == doc_id)
                )
            ) == 0
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(EntityMentionRecord)
                    .where(EntityMentionRecord.doc_id == doc_id)
                )
            ) == 0
            remaining_entities = (
                await session.execute(
                    select(EntityRecord.entity_id).where(
                        EntityRecord.entity_id.in_(entity_names.values())
                    )
                )
            ).scalars().all()
        assert not remaining_entities
        assert not await neo4j.document_graph_exists(doc_id)
        assert await qdrant.get_chunks_by_doc_id(doc_id) == {}

        after_delete_counts = await _neo4j_counts(neo4j)
        print(f"Step4 Neo4j counts after delete: {after_delete_counts}")
        assert after_delete_counts["nodes"] < after_ingest_counts["nodes"]
        assert await run_reconciliation(repair=False) == 0

        # Clean up the web document so subsequent tests see zero drift.
        async with get_session() as session:
            await DocumentRepository.delete_document(session, web_doc_id)
            await session.commit()
        await _drain_outbox()
        assert await run_reconciliation(repair=False) == 0
    finally:
        await graph.close()
        await qdrant.close()
        await neo4j.close()
