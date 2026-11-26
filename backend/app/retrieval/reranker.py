from collections.abc import Sequence
from functools import lru_cache
from typing import Any

from app.core.config import get_settings
from app.domain import Evidence
from app.runtime import RERANK_POOL, get_models, off_loop


class CrossEncoderReranker:
    """Reranker backed by the process-wide warmed CrossEncoder model."""

    def __init__(self, model_name: str | None = None, model: Any | None = None) -> None:
        settings = get_settings()
        self.model_name = model_name or settings.RERANKER_MODEL
        self._model = model

    @property
    def model(self) -> Any:
        """Return the warmed model owned by :class:`app.runtime.Models`."""
        if self._model is None:
            self._model = get_models().reranker
        return self._model

    async def rerank_evidence_async(
        self,
        query: str,
        candidates: Sequence[Evidence],
        top_k: int | None = None,
    ) -> list[Evidence]:
        """Run CrossEncoder inference on the dedicated pool, off the event loop."""
        settings = get_settings()
        timeout = min(settings.MODEL_INFERENCE_TIMEOUT_SECONDS, settings.RERANK_TIMEOUT_SECONDS)
        return await off_loop(
            self.rerank_evidence,
            query,
            list(candidates),
            top_k,
            timeout=timeout,
            pool=RERANK_POOL,
        )

    def predict_pairs(
        self, pairs: Sequence[tuple[str, str]], max_length: int | None = None
    ) -> list[float]:
        """Compute reranking scores for query-passage pairs."""
        if not pairs:
            return []
        settings = get_settings()
        scores = self.model.predict(
            list(pairs),
            max_length=settings.RERANK_MAX_LENGTH if max_length is None else max_length,
        )
        return [float(s) for s in scores]

    def rerank_evidence(
        self,
        query: str,
        candidates: Sequence[Evidence],
        top_k: int | None = None,
    ) -> list[Evidence]:
        """Score the top candidate head against the query and sort by score."""
        if not candidates:
            return []

        settings = get_settings()
        # Prefetching is wide so dense+sparse recall is high, but cross-encoding
        # every candidate is what caused the 5 s timeout. Only the fused head is
        # worth scoring for Ask latency.
        head = list(candidates)[: settings.RERANK_MAX_CANDIDATES]
        pairs = [(query, ev.text) for ev in head]
        scores = self.predict_pairs(pairs)

        reranked = [
            Evidence(
                chunk_id=ev.chunk_id,
                doc_id=ev.doc_id,
                text=ev.text,
                score=round(score, 5),
                retrieval_method="rerank",
                provenance=ev.provenance,
            )
            for ev, score in zip(head, scores, strict=True)
        ]

        reranked.sort(key=lambda x: x.score, reverse=True)
        if top_k is not None:
            return reranked[:top_k]
        return reranked


@lru_cache(maxsize=1)
def get_reranker() -> CrossEncoderReranker:
    """Singleton getter for the CrossEncoder reranker."""
    return CrossEncoderReranker()
