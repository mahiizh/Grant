import logging
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.invalidation import CacheInvalidator
from app.db.models import ChunkRecord, DocumentRecord, EntityMentionRecord
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
    mention_count = await session.scalar(
        select(func.count()).select_from(EntityMentionRecord).where(EntityMentionRecord.doc_id == doc_id)
    )
    remaining = int(doc_count or 0) + int(chunk_count or 0) + int(mention_count or 0)
    return StoreDeleteResult(store="PostgreSQL", remaining=remaining, cleared=remaining == 0)


async def _verify_qdrant_chunks(
    indexer: QdrantIndexer,
    expected_chunk_ids: set[str],
) -> StoreDeleteResult:
    present = await indexer.get_all_chunk_ids()
    remaining = len(expected_chunk_ids & present)
    return StoreDeleteResult(store="Qdrant", remaining=remaining, cleared=remaining == 0)


async def _verify_neo4j_document(
    indexer: Neo4jIndexer,
    doc_id: str,
) -> StoreDeleteResult:
    """Neo4j holds no chunk ids; verify the Document node and its edges are gone."""
    remaining = 1 if await indexer.document_graph_exists(doc_id) else 0
    return StoreDeleteResult(store="Neo4j", remaining=remaining, cleared=remaining == 0)


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

    try:
        results.append(await _verify_qdrant_chunks(qdrant, expected))
    except Exception as exc:  # pragma: no cover - defensive store guard
        logger.error("Failed verifying Qdrant deletion for %s: %s", doc_id, exc)
        results.append(
            StoreDeleteResult(store="Qdrant", remaining=-1, cleared=False, error=str(exc))
        )

    try:
        results.append(await _verify_neo4j_document(neo4j, doc_id))
    except Exception as exc:  # pragma: no cover - defensive store guard
        logger.error("Failed verifying Neo4j deletion for %s: %s", doc_id, exc)
        results.append(
            StoreDeleteResult(store="Neo4j", remaining=-1, cleared=False, error=str(exc))
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
