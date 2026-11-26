"""Embedding facade backed by the process-wide bounded model runtime."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from functools import lru_cache

from app.core.config import get_settings
from app.runtime import SparseVector, get_models, off_loop


def _dense_query(text: str) -> list[float]:
    return get_models().embed_query_dense(text)


def _dense_chunks(texts: Sequence[str]) -> list[list[float]]:
    return get_models().embed_chunks_dense(texts)


def _sparse_query(text: str) -> SparseVector:
    return get_models().embed_query_sparse(text)


def _sparse_chunks(texts: Sequence[str]) -> list[SparseVector]:
    return get_models().embed_chunks_sparse(texts)


class EmbeddingService:
    """Manages dense and sparse embeddings via the shared FastEmbed bundle."""

    def __init__(self) -> None:
        settings = get_settings()
        self.dense_model_name = settings.EMBEDDING_MODEL
        self.sparse_model_name = settings.SPARSE_MODEL
        self.dim = settings.EMBEDDING_DIM

    @staticmethod
    def _timeout() -> float:
        return get_settings().MODEL_INFERENCE_TIMEOUT_SECONDS

    def embed_query_dense(self, query: str) -> list[float]:
        """Generate normalized dense embedding for a single query."""
        return _dense_query(query)

    async def aembed_query_dense(self, query: str) -> list[float]:
        return await off_loop(_dense_query, query, timeout=self._timeout())

    def embed_chunks_dense(self, texts: Sequence[str]) -> list[list[float]]:
        """Generate normalized dense embeddings for chunks."""
        return _dense_chunks(texts)

    async def aembed_chunks_dense(self, texts: Sequence[str]) -> list[list[float]]:
        return await off_loop(_dense_chunks, texts, timeout=self._timeout())

    def embed_query_sparse(self, query: str) -> SparseVector:
        """Generate sparse BM25 token weights for a single query."""
        return _sparse_query(query)

    async def aembed_query_sparse(self, query: str) -> SparseVector:
        return await off_loop(_sparse_query, query, timeout=self._timeout())

    def embed_chunks_sparse(self, texts: Sequence[str]) -> list[SparseVector]:
        """Generate sparse BM25 token weights for multiple texts."""
        return _sparse_chunks(texts)

    async def aembed_chunks_sparse(self, texts: Sequence[str]) -> list[SparseVector]:
        return await off_loop(_sparse_chunks, texts, timeout=self._timeout())

    def embed_query(self, query: str) -> tuple[list[float], SparseVector]:
        """Embed a query into both dense and sparse representations."""
        return self.embed_query_dense(query), self.embed_query_sparse(query)

    async def aembed_query(self, query: str) -> tuple[list[float], SparseVector]:
        dense, sparse = await asyncio.gather(
            self.aembed_query_dense(query),
            self.aembed_query_sparse(query),
        )
        return dense, sparse


@lru_cache(maxsize=1)
def get_embedding_service() -> EmbeddingService:
    """Singleton getter for the embedding facade (model loading stays lazy)."""
    return EmbeddingService()
