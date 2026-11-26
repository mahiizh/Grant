"""Shared, bounded model runtime for the API process.

Local models are constructed once during the FastAPI lifespan, warmed before
traffic is accepted, and every blocking inference call runs on a small thread
pool instead of the event loop. CLI/test callers get a lazy singleton so they
also reuse one bundle per process.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Any, NamedTuple, TypeVar

import torch
from fastembed import SparseEmbedding, SparseTextEmbedding, TextEmbedding
from sentence_transformers import CrossEncoder

from app.core.config import get_settings

logger = logging.getLogger(__name__)

torch.set_num_threads(int(os.getenv("TORCH_THREADS", "4")))

MODEL_POOL = ThreadPoolExecutor(
    max_workers=int(os.getenv("MODEL_POOL_WORKERS", "2")),
    thread_name_prefix="model",
)

T = TypeVar("T")


async def off_loop(
    fn: Callable[..., T],
    *args: Any,
    timeout: float | None = None,
    **kwargs: Any,
) -> T:
    """Run a blocking model call on the bounded pool, never on the event loop."""
    loop = asyncio.get_running_loop()
    future = loop.run_in_executor(MODEL_POOL, partial(fn, *args, **kwargs))
    if timeout is None:
        return await future
    return await asyncio.wait_for(future, timeout=timeout)


class SparseVector(NamedTuple):
    indices: list[int]
    values: list[float]


class Models:
    """All dense/sparse/rerank inference models owned by the process."""

    def __init__(self) -> None:
        settings = get_settings()
        self.dense_model_name = settings.EMBEDDING_MODEL
        self.sparse_model_name = settings.SPARSE_MODEL
        self.rerank_model_name = settings.RERANKER_MODEL
        self.dim = settings.EMBEDDING_DIM

        self.dense = TextEmbedding(model_name=self.dense_model_name)
        self.sparse = SparseTextEmbedding(model_name=self.sparse_model_name)
        self.reranker = CrossEncoder(self.rerank_model_name)

        self.warmup()

    def warmup(self) -> None:
        """Load kernels and validate every model before traffic is accepted."""
        list(self.dense.embed(["warmup"]))
        list(self.sparse.embed(["warmup"]))
        self.reranker.predict([("warmup", "warmup passage")])

    @staticmethod
    def _sparse_vector(result: SparseEmbedding) -> SparseVector:
        return SparseVector(
            indices=[int(idx) for idx in result.indices],
            values=[float(value) for value in result.values],
        )

    def embed_query_dense(self, text: str) -> list[float]:
        return [float(value) for value in next(iter(self.dense.embed([text])))]

    def embed_chunks_dense(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        return [[float(value) for value in vector] for vector in self.dense.embed(texts)]

    def embed_query_sparse(self, text: str) -> SparseVector:
        return self._sparse_vector(next(iter(self.sparse.embed([text]))))

    def embed_chunks_sparse(self, texts: Sequence[str]) -> list[SparseVector]:
        if not texts:
            return []
        return [self._sparse_vector(result) for result in self.sparse.embed(texts)]

    def rerank(self, query: str, texts: Sequence[str]) -> list[float]:
        if not texts:
            return []
        scores = self.reranker.predict([(query, text) for text in texts])
        return [float(score) for score in scores]


_models: Models | None = None
_models_lock = threading.Lock()


def _build_models() -> Models:
    """Construction hook so tests can replace the real model load."""
    return Models()


def set_models(models: Models | None) -> None:
    """Install (or clear) the process-wide bundle."""
    global _models
    with _models_lock:
        _models = models


def get_models() -> Models:
    """Return the installed bundle, creating a lazy fallback outside the API."""
    global _models
    if _models is None:
        with _models_lock:
            if _models is None:
                _models = _build_models()
    return _models


async def startup_models() -> None:
    """Build and warm every local model once during lifespan startup."""
    settings = get_settings()
    if settings.APP_ENV == "test":
        logger.info("Test environment detected; skipping local model warmup.")
        return

    models = await off_loop(
        _build_models, timeout=settings.MODEL_STARTUP_TIMEOUT_SECONDS
    )
    set_models(models)
    logger.info(
        "Local models warmed once: dense=%s sparse=%s reranker=%s",
        models.dense_model_name,
        models.sparse_model_name,
        models.rerank_model_name,
    )


def shutdown_models() -> None:
    """Release the process-wide bundle on lifespan shutdown."""
    set_models(None)
