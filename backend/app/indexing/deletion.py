import logging
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.invalidation import CacheInvalidator
from app.db.models import ChunkRecord, DocumentRecord
from app.indexing.neo4j_indexer import Neo4jIndexer
from app.indexing.qdrant_indexer import QdrantIndexer

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StoreDeleteResult:
    """Outcome of deleting one document from one storage system."""

    store: str
    remaining: int
    cleared: bool
    error: str | None = None


async def _verify_postgres(session: AsyncSession, doc_id: str) -> StoreDeleteResult:
    doc_count = await session.scalar(
        select(func.count()).select_from(DocumentRecord).where(DocumentRecord.doc_id == doc_id)
    )
    chunk_count = await session.scalar(
        select(func.count()).select_from(ChunkRecord).where(ChunkRecord.doc_id == doc_id)
    )
    remaining = int(doc_count or 0) + int(chunk_count or 0)
    return StoreDeleteResult(store="PostgreSQL", remaining=remaining, cleared=remaining == 0)


async def _verify_chunk_store(
    store: str,
    indexer: QdrantIndexer | Neo4jIndexer,
    expected_chunk_ids: set[str],
) -> StoreDeleteResult:
    present = await indexer.get_all_chunk_ids()
    remaining = len(expected_chunk_ids & present)
    return StoreDeleteResult(store=store, remaining=remaining, cleared=remaining == 0)


async def verify_document_deleted(
    session: AsyncSession,
    doc_id: str,
    chunk_ids: Sequence[str],
    qdrant: QdrantIndexer,
    neo4j: Neo4jIndexer,
    invalidator: CacheInvalidator,
) -> list[StoreDeleteResult]:
    """Prove that a deleted document no longer exists in any storage system.

    A delete is only reported as successful when every store reports zero
    remaining rows/points/nodes/keys for the document. Each store is checked
    independently so a partial failure is visible instead of being masked by a
    hardcoded "all cleared" response.
    """
    expected = set(chunk_ids)
    results: list[StoreDeleteResult] = []

    try:
        results.append(await _verify_postgres(session, doc_id))
    except Exception as exc:  # pragma: no cover - defensive store guard
        logger.error("Failed verifying PostgreSQL deletion for %s: %s", doc_id, exc)
        results.append(
            StoreDeleteResult(store="PostgreSQL", remaining=-1, cleared=False, error=str(exc))
        )

    for store, indexer in (("Qdrant", qdrant), ("Neo4j", neo4j)):
        try:
            results.append(await _verify_chunk_store(store, indexer, expected))
        except Exception as exc:  # pragma: no cover - defensive store guard
            logger.error("Failed verifying %s deletion for %s: %s", store, doc_id, exc)
            results.append(
                StoreDeleteResult(store=store, remaining=-1, cleared=False, error=str(exc))
            )

    try:
        remaining_keys = invalidator.count_document_keys(doc_id)
        results.append(
            StoreDeleteResult(
                store="Redis",
                remaining=remaining_keys,
                cleared=remaining_keys == 0,
            )
        )
    except Exception as exc:  # pragma: no cover - defensive store guard
        logger.error("Failed verifying Redis deletion for %s: %s", doc_id, exc)
        results.append(
            StoreDeleteResult(store="Redis", remaining=-1, cleared=False, error=str(exc))
        )

    return results
