from collections.abc import Sequence
from typing import Any

from app.domain import Evidence, Provenance, SourceTier
from app.retrieval.dense import DenseRetriever
from app.retrieval.filters import RetrievalFilter
from app.retrieval.reranker import get_reranker
from app.retrieval.sparse import BM25Retriever


def reciprocal_rank_fusion(
    ranked_lists: Sequence[list[str]],
    rrf_k: int = 60,
) -> list[tuple[str, float]]:
    """Fuse multiple ranked candidate lists using Reciprocal Rank Fusion (RRF).

    Formula: RRF_score(d) = sum(1.0 / (rrf_k + rank_i(d))) for each list i.
    """
    scores: dict[str, float] = {}

    for ranked_list in ranked_lists:
        for rank, item_id in enumerate(ranked_list, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + (1.0 / (rrf_k + rank))

    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


class HybridRetriever:
    """Production Hybrid retriever combining dense and BM25 search via RRF and CrossEncoder rerank."""

    def __init__(
        self,
        dense_retriever: DenseRetriever | None = None,
        bm25_retriever: BM25Retriever | None = None,
        rrf_k: int = 60,
    ) -> None:
        self.dense = dense_retriever or DenseRetriever()
        self.sparse = bm25_retriever or BM25Retriever()
        self.rrf_k = rrf_k
        self.reranker = get_reranker()

    async def search(
        self,
        query: str,
        top_k: int = 10,
        filter_criteria: RetrievalFilter | None = None,
        rerank: bool = False,
    ) -> list[Evidence]:
        """Perform hybrid retrieval over real Qdrant collection and return Evidence objects."""
        # 1. Fetch dense candidates
        dense_candidates = await self.dense.search(
            query=query,
            top_k=top_k * 2,
            filter_criteria=filter_criteria,
        )
        dense_ranked_ids = [cid for cid, _, _ in dense_candidates]
        payloads: dict[str, dict[str, Any]] = {cid: p for cid, _, p in dense_candidates}

        # 2. Fetch sparse candidates
        sparse_candidates = await self.sparse.search(
            query=query,
            top_k=top_k * 2,
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
        )

        # 4. Construct Evidence items
        evidence_list: list[Evidence] = []
        for chunk_id, rrf_score in fused[: top_k * 2]:
            payload = payloads.get(chunk_id)
            if not payload:
                continue

            tier_val = payload.get("source_tier", 1)
            prov = Provenance(
                tier=SourceTier(tier_val),
                source_uri=payload.get("source_uri", payload.get("doc_id", "")),
                confidence=1.0,
                verified=True,
            )

            evidence_list.append(
                Evidence(
                    chunk_id=chunk_id,
                    doc_id=payload.get("doc_id", ""),
                    text=payload.get("text", ""),
                    score=round(rrf_score, 5),
                    retrieval_method="hybrid",
                    provenance=prov,
                )
            )

        # 5. Optional Cross-Encoder reranking
        if rerank and evidence_list:
            return self.reranker.rerank_evidence(query=query, candidates=evidence_list, top_k=top_k)

        return evidence_list[:top_k]
