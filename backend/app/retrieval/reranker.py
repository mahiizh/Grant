from collections.abc import Sequence
from functools import lru_cache

from sentence_transformers import CrossEncoder

from app.core.config import get_settings
from app.domain import Evidence


class CrossEncoderReranker:
    """Reranker using CrossEncoder model (e.g. cross-encoder/ms-marco-MiniLM-L-6-v2)."""

    def __init__(self, model_name: str | None = None) -> None:
        name = model_name or get_settings().RERANKER_MODEL
        self.model_name = name
        self._model = CrossEncoder(name)

    def predict_pairs(self, pairs: Sequence[tuple[str, str]]) -> list[float]:
        """Compute reranking scores for query-passage pairs."""
        if not pairs:
            return []
        scores = self._model.predict(list(pairs))
        return [float(s) for s in scores]

    def rerank_evidence(
        self,
        query: str,
        candidates: Sequence[Evidence],
        top_k: int | None = None,
    ) -> list[Evidence]:
        """Score candidate Evidence items against query using CrossEncoder and sort descending."""
        if not candidates:
            return []

        pairs = [(query, ev.text) for ev in candidates]
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
            for ev, score in zip(candidates, scores, strict=True)
        ]

        reranked.sort(key=lambda x: x.score, reverse=True)
        if top_k is not None:
            return reranked[:top_k]
        return reranked


@lru_cache(maxsize=1)
def get_reranker() -> CrossEncoderReranker:
    """Singleton getter for the CrossEncoder reranker."""
    return CrossEncoderReranker()
