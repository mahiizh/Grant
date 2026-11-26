import asyncio
import logging
import time
from collections.abc import Sequence
from typing import Any

from app.core.config import get_settings
from app.domain import Evidence, Provenance, SourceTier
from app.observability.stage_timing import timed_stage
from app.retrieval.dense import DenseRetriever
from app.retrieval.filters import RetrievalFilter
from app.retrieval.reranker import get_reranker
from app.retrieval.sparse import BM25Retriever
from app.runtime import off_loop

logger = logging.getLogger(__name__)


def reciprocal_rank_fusion(
    ranked_lists: Sequence[list[str]],
    rrf_k: int = 60,
    weights: Sequence[float] | None = None,
) -> list[tuple[str, float]]:
    """Fuse multiple ranked candidate lists using Reciprocal Rank Fusion (RRF).

    Formula: RRF_score(d) = sum(weight_i / (rrf_k + rank_i(d))) for each list i.
    """
    scores: dict[str, float] = {}
    effective_weights = [1.0] * len(ranked_lists) if weights is None else list(weights)

    for ranked_list, weight in zip(ranked_lists, effective_weights, strict=False):
        for rank, item_id in enumerate(ranked_list, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + (weight / (rrf_k + rank))

    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


class HybridRetriever:
    """Production Hybrid retriever combining dense and BM25 search via RRF and CrossEncoder rerank."""

    def __init__(
        self,
        dense_retriever: DenseRetriever | None = None,
        bm25_retriever: BM25Retriever | None = None,
        rrf_k: int | None = None,
        prefetch_multiplier: int | None = None,
        reranker: Any | None = None,
        rerank_timeout_seconds: float | None = None,
    ) -> None:
        settings = get_settings()
        self.dense = dense_retriever or DenseRetriever()
        self.sparse = bm25_retriever or BM25Retriever()
        self.rrf_k = rrf_k if rrf_k is not None else settings.RRF_K
        self.prefetch_multiplier = (
            prefetch_multiplier
            if prefetch_multiplier is not None
            else settings.HYBRID_PREFETCH_MULTIPLIER
        )
        self.rerank_timeout_seconds = (
            rerank_timeout_seconds
            if rerank_timeout_seconds is not None
            else settings.RERANK_TIMEOUT_SECONDS
        )
        self.reranker = reranker or get_reranker()

    def _to_evidence(
        self,
        chunk_id: str,
        score: float,
        payload: dict[str, Any],
        method: str,
        filter_criteria: RetrievalFilter | None,
    ) -> Evidence | None:
        """Build Evidence from a Qdrant payload, refusing denied payloads."""
        if filter_criteria is not None and not filter_criteria.permits_payload(payload):
            return None

        tier_val = payload.get("source_tier", 1)
        prov = Provenance(
            tier=SourceTier(tier_val),
            source_uri=payload.get("source_uri", payload.get("doc_id", "")),
            confidence=1.0,
            verified=True,
        )
        return Evidence(
            chunk_id=chunk_id,
            doc_id=payload.get("doc_id", ""),
            text=payload.get("text", ""),
            score=round(score, 5),
            retrieval_method=method,
            provenance=prov,
        )

    async def search_dense(
        self,
        query: str,
        top_k: int = 10,
        filter_criteria: RetrievalFilter | None = None,
    ) -> list[Evidence]:
        """Dense-only retrieval, used by the ``dense`` baseline configuration."""
        candidates = await self.dense.search(
            query=query,
            top_k=top_k,
            filter_criteria=filter_criteria,
        )
        evidence: list[Evidence] = []
        for chunk_id, score, payload in candidates:
            item = self._to_evidence(chunk_id, score, payload, "dense", filter_criteria)
            if item is not None:
                evidence.append(item)
        return evidence

    async def search_sparse(
        self,
        query: str,
        top_k: int = 10,
        filter_criteria: RetrievalFilter | None = None,
    ) -> list[Evidence]:
        """Sparse-only retrieval, used by the ``sparse`` baseline configuration."""
        candidates = await self.sparse.search(
            query=query,
            top_k=top_k,
            filter_criteria=filter_criteria,
        )
        evidence: list[Evidence] = []
        for chunk_id, score, payload in candidates:
            item = self._to_evidence(chunk_id, score, payload, "sparse", filter_criteria)
            if item is not None:
                evidence.append(item)
        return evidence

    async def search(
        self,
        query: str,
        top_k: int = 10,
        filter_criteria: RetrievalFilter | None = None,
        rerank: bool = False,
        extra_candidates: Sequence[Evidence] | None = None,
        prefetch_k: int | None = None,
        weights: Sequence[float] | None = None,
    ) -> list[Evidence]:
        """Perform hybrid retrieval over real Qdrant collection and return Evidence objects.

        ``extra_candidates`` lets a caller add another retrieval branch (for
        example graph path evidence) to the same rerank pool. The combined list
        is deduplicated, reranked once, and only then cut to ``top_k``.
        """
        prefetch_limit = prefetch_k if prefetch_k is not None else top_k * self.prefetch_multiplier

        # 1. Fetch dense candidates
        dense_candidates = await self.dense.search(
            query=query,
            top_k=prefetch_limit,
            filter_criteria=filter_criteria,
        )
        dense_ranked_ids = [cid for cid, _, _ in dense_candidates]
        # Qdrant returns cosine similarity for the dense vector. RRF scores are
        # rank-derived and cannot express relevance, so carry the dense cosine
        # alongside the fused ordering and use it as the evidence score.
        dense_scores: dict[str, float] = {cid: float(score) for cid, score, _ in dense_candidates}
        payloads: dict[str, dict[str, Any]] = {cid: p for cid, _, p in dense_candidates}

        # 2. Fetch sparse candidates
        sparse_candidates = await self.sparse.search(
            query=query,
            top_k=prefetch_limit,
            filter_criteria=filter_criteria,
        )
        sparse_ranked_ids = [cid for cid, _, _ in sparse_candidates]
        for cid, _, p in sparse_candidates:
            if cid not in payloads:
                payloads[cid] = p

        # 3. Reciprocal Rank Fusion
        fused = reciprocal_rank_fusion(
            ranked_lists=[dense_ranked_ids, sparse_ranked_ids],
            rrf_k=self.rrf_k,
            weights=weights,
        )

        # 4. Construct Evidence items in fused rank order, but score them by
        # dense cosine similarity instead of the rank-only RRF value.
        evidence_list: list[Evidence] = []
        for chunk_id, _rrf_score in fused[:prefetch_limit]:
            payload = payloads.get(chunk_id)
            if not payload:
                continue
            # Defense-in-depth: never build Evidence from a payload the filter denies,
            # even if a retriever upstream forgot to apply the ACL predicate.
            item = self._to_evidence(
                chunk_id,
                dense_scores.get(chunk_id, 0.0),
                payload,
                "hybrid",
                filter_criteria,
            )
            if item is not None:
                evidence_list.append(item)

        # 4b. Add candidates from any other branch (e.g. graph path evidence)
        # to the same rerank pool. Deduplicate by chunk id so a chunk found by
        # both branches is scored once.
        if extra_candidates:
            seen_chunk_ids = {item.chunk_id for item in evidence_list}
            for item in extra_candidates:
                if item.chunk_id not in seen_chunk_ids:
                    evidence_list.append(item)
                    seen_chunk_ids.add(item.chunk_id)

        # 5. Optional Cross-Encoder reranking over the combined candidate pool.
        # When disabled, fused order with dense cosine scores is the decision
        # path. A timeout degrades the same way, never to rank-only RRF values.
        if rerank and get_settings().RERANK_ENABLED and evidence_list:
            async def _rerank() -> list[Evidence]:
                rerank_async = getattr(self.reranker, "rerank_evidence_async", None)
                if rerank_async is not None:
                    return await rerank_async(
                        query=query, candidates=evidence_list, top_k=top_k
                    )
                return await off_loop(
                    self.reranker.rerank_evidence,
                    query=query,
                    candidates=evidence_list,
                    top_k=top_k,
                )

            started = time.perf_counter()
            try:
                async with timed_stage("rerank"):
                    return await asyncio.wait_for(
                        _rerank(), timeout=self.rerank_timeout_seconds
                    )
            except TimeoutError:
                elapsed_ms = (time.perf_counter() - started) * 1000.0
                logger.warning(
                    "Reranking timed out after %.1f ms (configured %.1f ms, %d candidates, "
                    "query=%r); returning fused retrieval order",
                    elapsed_ms,
                    self.rerank_timeout_seconds * 1000.0,
                    len(evidence_list),
                    query[:120],
                )
                return evidence_list[:top_k]

        return evidence_list[:top_k]
