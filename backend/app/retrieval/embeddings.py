from collections.abc import Sequence
from functools import lru_cache
from typing import NamedTuple

from fastembed import SparseEmbedding, SparseTextEmbedding, TextEmbedding

from app.core.config import get_settings


class SparseVector(NamedTuple):
    indices: list[int]
    values: list[float]


class EmbeddingService:
    """Manages dense and sparse embeddings via FastEmbed."""

    def __init__(self) -> None:
        settings = get_settings()
        self.dense_model_name = settings.EMBEDDING_MODEL
        self.sparse_model_name = settings.SPARSE_MODEL
        self.dim = settings.EMBEDDING_DIM

        self._dense_model = TextEmbedding(model_name=self.dense_model_name)
        self._sparse_model = SparseTextEmbedding(model_name=self.sparse_model_name)

    def embed_query_dense(self, query: str) -> list[float]:
        """Generate normalized dense embedding for a single query."""
        vectors = list(self._dense_model.embed([query]))
        return [float(x) for x in vectors[0]]

    def embed_chunks_dense(self, texts: Sequence[str]) -> list[list[float]]:
        """Generate normalized dense embeddings for chunks."""
        if not texts:
            return []
        vectors = list(self._dense_model.embed(texts))
        return [[float(x) for x in v] for v in vectors]

    def embed_query_sparse(self, query: str) -> SparseVector:
        """Generate sparse BM25 token weights for a single query."""
        results: list[SparseEmbedding] = list(self._sparse_model.embed([query]))
        res = results[0]
        return SparseVector(
            indices=[int(idx) for idx in res.indices],
            values=[float(val) for val in res.values],
        )

    def embed_chunks_sparse(self, texts: Sequence[str]) -> list[SparseVector]:
        """Generate sparse BM25 token weights for multiple texts."""
        if not texts:
            return []
        results: list[SparseEmbedding] = list(self._sparse_model.embed(texts))
        return [
            SparseVector(
                indices=[int(idx) for idx in res.indices],
                values=[float(val) for val in res.values],
            )
            for res in results
        ]

    def embed_query(self, query: str) -> tuple[list[float], SparseVector]:
        """Embed a query into both dense and sparse representations."""
        return self.embed_query_dense(query), self.embed_query_sparse(query)


@lru_cache(maxsize=1)
def get_embedding_service() -> EmbeddingService:
    """Singleton getter for the FastEmbed embedding service."""
    return EmbeddingService()
