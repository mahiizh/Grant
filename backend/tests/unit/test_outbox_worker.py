from collections.abc import AsyncGenerator
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.cache.invalidation import CacheInvalidator
from app.core.acl import ACLScope
from app.db.models import Base
from app.db.outbox import OutboxEventType, OutboxService, OutboxStatus
from app.db.postgres import DocumentRepository
from app.domain import Chunk, Document, Provenance, TemporalBounds
from app.indexing import Neo4jIndexer, OutboxWorker, QdrantIndexer
from tests.fakes.in_memory_indexers import FakeNeo4jIndexer, FakeQdrantIndexer


class _NoopInvalidator:
    """Avoid a real Redis connection when exercising deletion events."""

    def handle_outbox_event(self, event_type: str, payload: dict[str, object]) -> dict[str, object]:
        return {"invalidated": True}


@pytest.fixture
async def test_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide an isolated, in-memory SQLite database session."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.anyio
async def test_outbox_worker_processes_chunks(test_session: AsyncSession) -> None:
    # 1. Stage chunks in Postgres
    now = TemporalBounds.current()
    prov = Provenance.from_document("corpus/rfc_001.md")
    acl = ACLScope.public()

    chunk_1 = Chunk(
        chunk_id="chk_001",
        doc_id="doc_sync_test",
        index=0,
        text="Sample chunk for vector indexing",
        acl_scope=acl,
        temporal=now,
        provenance=prov,
    )
    doc = Document(
        doc_id="doc_sync_test",
        title="Sync Test Doc",
        content="Sample chunk for vector indexing",
        chunks=[chunk_1],
        acl_scope=acl,
        temporal=now,
        provenance=prov,
    )
    await DocumentRepository.save_document(session=test_session, document=doc)
    await test_session.flush()

    # Verify pending events exist
    pending = await OutboxService.fetch_pending_events(session=test_session, limit=10)
    assert len(pending) == 2  # 1 doc + 1 chunk

    # 2. Run Outbox Worker
    qdrant = FakeQdrantIndexer()
    neo4j = FakeNeo4jIndexer()
    worker = OutboxWorker(
        qdrant_indexer=cast(QdrantIndexer, qdrant),
        neo4j_indexer=cast(Neo4jIndexer, neo4j),
    )

    processed_count = await worker.process_batch(session=test_session, batch_size=10)
    await test_session.flush()

    assert processed_count == 2
    # Verify chunk was pushed to Qdrant
    assert qdrant.count() == 1
    stored_chunk = qdrant.get_chunk("chk_001")
    assert stored_chunk is not None
    assert stored_chunk["text"] == "Sample chunk for vector indexing"

    # Verify no pending events remain
    remaining = await OutboxService.fetch_pending_events(session=test_session, limit=10)
    assert len(remaining) == 0


@pytest.mark.anyio
async def test_outbox_worker_processes_deletion(test_session: AsyncSession) -> None:
    now = TemporalBounds.current()
    prov = Provenance.from_document("corpus/rfc_001.md")
    acl = ACLScope.public()

    chunk_1 = Chunk(
        chunk_id="chk_del_01",
        doc_id="doc_del_test",
        index=0,
        text="Deletable chunk",
        acl_scope=acl,
        temporal=now,
        provenance=prov,
    )
    doc = Document(
        doc_id="doc_del_test",
        title="Deletion Doc",
        content="Deletable chunk",
        chunks=[chunk_1],
        acl_scope=acl,
        temporal=now,
        provenance=prov,
    )
    await DocumentRepository.save_document(session=test_session, document=doc)
    await test_session.flush()

    qdrant = FakeQdrantIndexer()
    neo4j = FakeNeo4jIndexer()
    worker = OutboxWorker(
        qdrant_indexer=cast(QdrantIndexer, qdrant),
        neo4j_indexer=cast(Neo4jIndexer, neo4j),
        cache_invalidator=cast(CacheInvalidator, _NoopInvalidator()),
    )

    # Process creation
    await worker.process_batch(session=test_session, batch_size=10)
    await test_session.flush()
    assert qdrant.count() == 1

    # Delete document
    await DocumentRepository.delete_document(session=test_session, doc_id="doc_del_test")
    await test_session.flush()

    # Process deletion outbox events
    await worker.process_batch(session=test_session, batch_size=10)
    await test_session.flush()

    # Verify chunk removed from Qdrant
    assert qdrant.count() == 0


@pytest.mark.anyio
async def test_outbox_worker_error_handling(test_session: AsyncSession) -> None:
    # Stage a single event directly
    event = OutboxService.stage_event(
        session=test_session,
        event_type=OutboxEventType.CHUNK_UPSERTED,
        aggregate_type="chunk",
        aggregate_id="chk_err",
        payload={"chunk_id": "chk_err"},
    )
    await test_session.flush()

    # Mock indexer that raises an exception
    class FailingQdrant(FakeQdrantIndexer):
        async def upsert_chunk(self, *args: object, **kwargs: object) -> None:
            raise ConnectionError("Qdrant service unreachable")

    worker = OutboxWorker(qdrant_indexer=cast(QdrantIndexer, FailingQdrant()))
    success = await worker.process_event(session=test_session, event=event)
    await test_session.flush()

    assert not success
    assert event.status == OutboxStatus.FAILED.value
    assert event.retry_count == 1
    assert "Qdrant service unreachable" in (event.last_error or "")


@pytest.mark.anyio
async def test_outbox_worker_handles_cache_invalidation(test_session: AsyncSession) -> None:
    class RecordingInvalidator:
        def __init__(self) -> None:
            self.events: list[tuple[str, dict[str, object]]] = []

        def handle_outbox_event(
            self, event_type: str, payload: dict[str, object]
        ) -> dict[str, object]:
            self.events.append((event_type, payload))
            return {"invalidated": True}

    invalidator = RecordingInvalidator()
    event = OutboxService.stage_event(
        session=test_session,
        event_type=OutboxEventType.CACHE_INVALIDATED,
        aggregate_type="cache",
        aggregate_id="doc_cache",
        payload={"doc_id": "doc_cache", "reason": "document_deletion"},
    )
    await test_session.flush()

    worker = OutboxWorker(cache_invalidator=cast(CacheInvalidator, invalidator))
    success = await worker.process_event(session=test_session, event=event)
    await test_session.flush()

    assert success
    assert event.status == OutboxStatus.PROCESSED.value
    assert invalidator.events == [
        ("CACHE_INVALIDATED", {"doc_id": "doc_cache", "reason": "document_deletion"})
    ]
