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
from pathlib import Path
from typing import Any, NamedTuple, TypeVar

import onnxruntime as ort
import torch
from fastembed import SparseEmbedding, SparseTextEmbedding, TextEmbedding
from huggingface_hub import snapshot_download
from transformers import AutoTokenizer

from app.core.config import get_settings

logger = logging.getLogger(__name__)

torch.set_num_threads(int(os.getenv("TORCH_THREADS", "4")))

MODEL_POOL = ThreadPoolExecutor(
    max_workers=int(os.getenv("MODEL_POOL_WORKERS", "2")),
    thread_name_prefix="model",
)

# Reranking has its own executor. Sharing MODEL_POOL made a warm cross-encoder
# wait behind embedding work and pushed every Ask into the rerank timeout.
RERANK_POOL = ThreadPoolExecutor(
    max_workers=int(os.getenv("RERANK_POOL_WORKERS", "1")),
    thread_name_prefix="rerank",
)

T = TypeVar("T")


async def off_loop(
    fn: Callable[..., T],
    *args: Any,
    timeout: float | None = None,
    pool: ThreadPoolExecutor | None = None,
    **kwargs: Any,
) -> T:
    """Run a blocking model call on a bounded pool, never on the event loop."""
    loop = asyncio.get_running_loop()
    future = loop.run_in_executor(pool or MODEL_POOL, partial(fn, *args, **kwargs))
    if timeout is None:
        return await future
    return await asyncio.wait_for(future, timeout=timeout)


class SparseVector(NamedTuple):
    indices: list[int]
    values: list[float]


class OnnxCrossEncoder:
    """Quantized ONNX cross-encoder used for bounded reranking."""

    _INPUT_NAMES = ("input_ids", "attention_mask", "token_type_ids")

    def __init__(self, model_name: str, max_length: int) -> None:
        root = Path(
            snapshot_download(
                model_name,
                allow_patterns=[
                    "onnx/model_quantized.onnx",
                    "tokenizer.json",
                    "tokenizer_config.json",
                    "special_tokens_map.json",
                    "vocab.txt",
                    "config.json",
                ],
            )
        )
        self.model_name = model_name
        self.max_length = max_length
        self.tokenizer = AutoTokenizer.from_pretrained(str(root))
        self.session = ort.InferenceSession(
            str(root / "onnx" / "model_quantized.onnx"),
            providers=["CPUExecutionProvider"],
        )
        available = {item.name for item in self.session.get_inputs()}
        self.input_names = [name for name in self._INPUT_NAMES if name in available]

    def predict(
        self, pairs: Sequence[tuple[str, str]], max_length: int | None = None
    ) -> list[float]:
        if not pairs:
            return []
        encoded = self.tokenizer(
            list(pairs),
            max_length=max_length or self.max_length,
            padding=True,
            truncation=True,
            return_tensors="np",
        )
        feed = {name: encoded[name] for name in self.input_names}
        logits = self.session.run(None, feed)[0]
        return [float(score) for score in logits.reshape(-1)]


class Models:
    """All dense/sparse/rerank inference models owned by the process."""

    def __init__(self) -> None:
        settings = get_settings()
        self.dense_model_name = settings.EMBEDDING_MODEL
        self.sparse_model_name = settings.SPARSE_MODEL
        self.rerank_model_name = settings.RERANK_ONNX_MODEL
        self.dim = settings.EMBEDDING_DIM

        self.dense = TextEmbedding(model_name=self.dense_model_name)
        self.sparse = SparseTextEmbedding(model_name=self.sparse_model_name)
        self.reranker = OnnxCrossEncoder(
            self.rerank_model_name, settings.RERANK_MAX_LENGTH
        )

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
        scores = self.reranker.predict(
            [(query, text) for text in texts],
            max_length=get_settings().RERANK_MAX_LENGTH,
        )
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
