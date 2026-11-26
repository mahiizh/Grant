import json
from collections.abc import AsyncGenerator
from typing import Any, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.cache.invalidation import CacheInvalidator
from app.core.acl import ACLScope
from app.db.models import Base
from app.db.postgres import DocumentRepository
from datetime import UTC, datetime

from app.domain import Chunk, Document, Provenance
from app.indexing import Neo4jIndexer, OutboxWorker, QdrantIndexer
from app.indexing.deletion import verify_document_deleted
from tests.fakes.fake_redis import FakeRedis
from tests.fakes.in_memory_indexers import FakeNeo4jIndexer, FakeQdrantIndexer


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


def _build_document() -> Document:
    now = datetime(2026, 4, 1, tzinfo=UTC)
    prov = Provenance.from_document("corpus/deletion.md")
    acl = ACLScope.public()
    chunks = [
        Chunk(
            chunk_id=f"chk_del_{index}",
            doc_id="doc_del",
            index=index,
            text=f"Deletable chunk {index}",
            acl_scope=acl,
            ingested_at=now,
            provenance=prov,
        )
        for index in range(2)
    ]
    return Document(
        doc_id="doc_del",
        title="Deletion Doc",
        content="Deletable chunk 0\nDeletable chunk 1",
        chunks=chunks,
        acl_scope=acl,
        ingested_at=now,
        provenance=prov,
    )


async def _seed_indexes(
    session: AsyncSession,
    qdrant: FakeQdrantIndexer,
    neo4j: FakeNeo4jIndexer,
) -> None:
    await DocumentRepository.save_document(session=session, document=_build_document())
    await session.flush()
    worker = OutboxWorker(
        qdrant_indexer=cast(QdrantIndexer, qdrant),
        neo4j_indexer=cast(Neo4jIndexer, neo4j),
        cache_invalidator=CacheInvalidator(redis_client=cast(Any, FakeRedis())),
    )
    await _drain(session, worker)


async def _drain(session: AsyncSession, worker: OutboxWorker) -> None:
    while True:
        processed = await worker.process_batch(session=session, batch_size=50)
        await session.flush()
        if processed == 0:
            return


@pytest.mark.anyio
async def test_verified_delete_clears_every_store(test_session: AsyncSession) -> None:
    qdrant = FakeQdrantIndexer()
    neo4j = FakeNeo4jIndexer()
    redis = FakeRedis()
    invalidator = CacheInvalidator(redis_client=cast(Any, redis))

    await _seed_indexes(test_session, qdrant, neo4j)
    assert qdrant.count() == 2
    assert await neo4j.get_all_document_ids() == {"doc_del"}

    redis.seed(
        "exact:stale",
        json.dumps(
            {"query": "q", "answer": "a", "evidence": [{"doc_id": "doc_del", "chunk_id": "c"}]}
        ),
    )

    deleted = await DocumentRepository.delete_document(session=test_session, doc_id="doc_del")
    assert deleted
    await test_session.flush()

    worker = OutboxWorker(
        qdrant_indexer=cast(QdrantIndexer, qdrant),
        neo4j_indexer=cast(Neo4jIndexer, neo4j),
        cache_invalidator=invalidator,
    )
    await _drain(test_session, worker)

    results = await verify_document_deleted(
        session=test_session,
        doc_id="doc_del",
        chunk_ids=["chk_del_0", "chk_del_1"],
        qdrant=cast(QdrantIndexer, qdrant),
        neo4j=cast(Neo4jIndexer, neo4j),
        invalidator=invalidator,
    )

    assert [(r.store, r.remaining, r.cleared) for r in results] == [
        ("PostgreSQL", 0, True),
        ("Qdrant", 0, True),
        ("Neo4j", 0, True),
        ("Redis", 0, True),
    ]
    assert all(r.error is None for r in results)


@pytest.mark.anyio
async def test_verified_delete_reports_leftover_chunk(test_session: AsyncSession) -> None:
    qdrant = FakeQdrantIndexer()
    neo4j = FakeNeo4jIndexer()
    redis = FakeRedis()
    invalidator = CacheInvalidator(redis_client=cast(Any, redis))

    await _seed_indexes(test_session, qdrant, neo4j)
    await DocumentRepository.delete_document(session=test_session, doc_id="doc_del")
    await test_session.flush()
    await _drain(
        test_session,
        OutboxWorker(
            qdrant_indexer=cast(QdrantIndexer, qdrant),
            neo4j_indexer=cast(Neo4jIndexer, neo4j),
            cache_invalidator=invalidator,
        ),
    )

    # Simulate a partial failure: one chunk survives in Qdrant.
    await qdrant.upsert_chunk(
        chunk_id="chk_del_0",
        doc_id="doc_del",
        text="orphan",
        payload={},
    )

    results = await verify_document_deleted(
        session=test_session,
        doc_id="doc_del",
        chunk_ids=["chk_del_0", "chk_del_1"],
        qdrant=cast(QdrantIndexer, qdrant),
        neo4j=cast(Neo4jIndexer, neo4j),
        invalidator=invalidator,
    )

    by_store = {r.store: r for r in results}
    assert by_store["PostgreSQL"].cleared
    assert by_store["Qdrant"].cleared is False
    assert by_store["Qdrant"].remaining == 1
    assert by_store["Neo4j"].cleared
    assert by_store["Redis"].cleared


@pytest.mark.anyio
async def test_verified_delete_reports_stale_cache_keys(test_session: AsyncSession) -> None:
    qdrant = FakeQdrantIndexer()
    neo4j = FakeNeo4jIndexer()
    redis = FakeRedis()
    invalidator = CacheInvalidator(redis_client=cast(Any, redis))

    await _seed_indexes(test_session, qdrant, neo4j)
    await DocumentRepository.delete_document(session=test_session, doc_id="doc_del")
    await test_session.flush()

    # A cache entry written after invalidation still cites the deleted doc.
    redis.seed(
        "exact:late",
        json.dumps(
            {"query": "q", "answer": "a", "evidence": [{"doc_id": "doc_del", "chunk_id": "c"}]}
        ),
    )

    results = await verify_document_deleted(
        session=test_session,
        doc_id="doc_del",
        chunk_ids=["chk_del_0", "chk_del_1"],
        qdrant=cast(QdrantIndexer, qdrant),
        neo4j=cast(Neo4jIndexer, neo4j),
        invalidator=invalidator,
    )

    by_store = {r.store: r for r in results}
    assert by_store["Redis"].cleared is False
    assert by_store["Redis"].remaining == 1
