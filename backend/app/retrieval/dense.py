import logging
from typing import Any

from qdrant_client import AsyncQdrantClient

from app.core.config import get_settings
from app.retrieval.embeddings import get_embedding_service
from app.retrieval.filters import RetrievalFilter

logger = logging.getLogger(__name__)


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Calculate the cosine similarity between two normalized vectors."""
    dot = sum(a * b for a, b in zip(vec_a, vec_b, strict=False))
    return max(0.0, min(1.0, dot))


def text_to_embedding(text: str, dim: int = 384) -> list[float]:
    """Helper to compute normalized dense embedding using FastEmbed."""
    emb = get_embedding_service()
    return emb.embed_query_dense(text)


class DenseRetriever:
    """Production Dense retriever querying Qdrant with FastEmbed BGE-small embeddings."""

    def __init__(self, client: AsyncQdrantClient | None = None) -> None:
        settings = get_settings()
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
        """Query Qdrant dense vector index and apply ACL/temporal payload filtering."""
        dense_vec = self.embedding_service.embed_query_dense(query)

        # Retrieve candidates with oversampling for post-filtering
        oversample = top_k * 3
        try:
            results = await self.client.query_points(
                collection_name=self.collection_name,
                query=dense_vec,
                using="dense",
                limit=oversample,
                with_payload=True,
            )
        except Exception as e:
            logger.error("Dense vector search failed: %s", e)
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
