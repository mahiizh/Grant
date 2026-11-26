import logging
import re
from typing import Any

from qdrant_client import AsyncQdrantClient, models

from app.core.config import get_settings
from app.core.store_guard import assert_writable_stores
from app.retrieval.embeddings import get_embedding_service
from app.retrieval.filters import RetrievalFilter

logger = logging.getLogger(__name__)


def tokenize(text: str) -> list[str]:
    """Normalize and tokenize text by splitting on whitespace and punctuation."""
    cleaned = re.sub(r"[^\w\s-]", " ", text.lower())
    return [t for t in cleaned.split() if len(t) > 1]


class BM25Retriever:
    """Production BM25 sparse retriever querying Qdrant sparse vectors."""

    def __init__(self, client: AsyncQdrantClient | None = None) -> None:
        settings = get_settings()
        assert_writable_stores(settings)
        self.collection_name = settings.QDRANT_COLLECTION
        self.client = client or AsyncQdrantClient(
            url=f"http://{settings.QDRANT_HOST}:{settings.QDRANT_PORT}",
            check_compatibility=False,
        )
        self.embedding_service = get_embedding_service()

    async def search(
        self,
        query: str,
        top_k: int = 10,
        filter_criteria: RetrievalFilter | None = None,
    ) -> list[tuple[str, float, dict[str, Any]]]:
        """Query Qdrant sparse BM25 vector index with ACL/temporal payload filtering."""
        sparse_vec = self.embedding_service.embed_query_sparse(query)
        if not sparse_vec.indices:
            return []

        query_filter = filter_criteria.to_qdrant_filter() if filter_criteria is not None else None
        try:
            results = await self.client.query_points(
                collection_name=self.collection_name,
                query=models.SparseVector(
                    indices=sparse_vec.indices,
                    values=sparse_vec.values,
                ),
                using="sparse",
                query_filter=query_filter,
                limit=top_k,
                with_payload=True,
            )
        except Exception as e:
            logger.error("Sparse BM25 search failed: %s", e)
            return []

        filtered_results: list[tuple[str, float, dict[str, Any]]] = []
        for point in results.points:
            payload = point.payload or {}
            chunk_id = payload.get("chunk_id", str(point.id))

            if filter_criteria is not None and not filter_criteria.permits_payload(payload):
                continue

            filtered_results.append((chunk_id, float(point.score), payload))
            if len(filtered_results) >= top_k:
                break

        return filtered_results
