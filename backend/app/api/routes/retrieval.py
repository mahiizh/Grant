import logging
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.api.schemas.retrieval import RetrievalCandidate, RetrievalCompareResponse
from app.core.auth import AuthenticatedUser, get_current_user
from app.retrieval.dense import DenseRetriever
from app.retrieval.hybrid import reciprocal_rank_fusion
from app.retrieval.reranker import CrossEncoderReranker, get_reranker
from app.retrieval.sparse import BM25Retriever

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/retrieval", tags=["retrieval"])


def get_dense_retriever() -> DenseRetriever:
    return DenseRetriever()


def get_sparse_retriever() -> BM25Retriever:
    return BM25Retriever()


@router.get("/compare", response_model=RetrievalCompareResponse)
async def compare_retrieval(
    query: str = Query("Transactional Outbox postgres failure"),
    k: int = Query(60),
    vector_cutoff: float = Query(0.40),
    cross_encoder_cutoff: float = Query(0.0),
    scope: str | None = Query(None),
    current_user: AuthenticatedUser = Depends(get_current_user),
    dense_retriever: DenseRetriever = Depends(get_dense_retriever),
    sparse_retriever: BM25Retriever = Depends(get_sparse_retriever),
    reranker: CrossEncoderReranker = Depends(get_reranker),
) -> RetrievalCompareResponse:
    """Compare candidate ranking across vector, sparse, RRF and cross-encoder rerankers."""
    filter_criteria = current_user.to_retrieval_filter(scope)

    # 1. Fetch dense candidates from Qdrant
    dense_candidates = await dense_retriever.search(
        query=query, top_k=15, filter_criteria=filter_criteria
    )
    dense_scores = {cid: score for cid, score, _ in dense_candidates}
    dense_ranked = [cid for cid, _, _ in dense_candidates]

    # 2. Fetch sparse candidates from Qdrant
    sparse_candidates = await sparse_retriever.search(
        query=query, top_k=15, filter_criteria=filter_criteria
    )
    sparse_scores = {cid: score for cid, score, _ in sparse_candidates}
    sparse_ranked = [cid for cid, _, _ in sparse_candidates]

    # Map payload texts
    all_payloads: dict[str, dict[str, Any]] = {}
    for cid, _, p in dense_candidates:
        all_payloads[cid] = p
    for cid, _, p in sparse_candidates:
        if cid not in all_payloads:
            all_payloads[cid] = p

    # 3. Fuse via RRF
    fused = reciprocal_rank_fusion(
        ranked_lists=[dense_ranked, sparse_ranked],
        rrf_k=k,
    )
    fused_scores = dict(fused)

    # Defense-in-depth: even if a retriever regresses, never score a denied payload.
    all_chunk_ids = [
        cid
        for cid in fused_scores
        if cid in all_payloads and filter_criteria.permits_payload(all_payloads[cid])
    ]
    if not all_chunk_ids:
        return RetrievalCompareResponse(
            query=query,
            rrf_k=k,
            vector_cutoff=vector_cutoff,
            cross_encoder_cutoff=cross_encoder_cutoff,
            candidates=[],
            total_candidates=0,
        )

    # 4. Predict CrossEncoder scores
    pairs = [(query, all_payloads[cid].get("text", "")) for cid in all_chunk_ids]
    ce_scores = reranker.predict_pairs(pairs)

    # 5. Build candidates and sort by CrossEncoder score descending
    raw_candidates = []
    for cid, ce_score in zip(all_chunk_ids, ce_scores, strict=False):
        payload = all_payloads.get(cid, {})
        raw_candidates.append(
            {
                "chunk_id": cid,
                "doc_title": payload.get("doc_id", "Unknown"),
                "text": payload.get("text", "")[:240],
                "vector_score": round(dense_scores.get(cid, 0.0), 4),
                "bm25_score": round(sparse_scores.get(cid, 0.0), 4),
                "graph_hops": 1
                if "INC" in payload.get("text", "") or "RFC" in payload.get("text", "")
                else 0,
                "rrf_score": round(fused_scores.get(cid, 0.0), 5),
                "cross_encoder_score": round(float(ce_score), 4),
            }
        )

    raw_candidates.sort(key=lambda x: x["cross_encoder_score"], reverse=True)

    candidates: list[RetrievalCandidate] = []
    for rank, item in enumerate(raw_candidates, start=1):
        included = item["cross_encoder_score"] >= cross_encoder_cutoff or rank <= 3
        candidates.append(
            RetrievalCandidate(
                chunk_id=item["chunk_id"],
                doc_title=item["doc_title"],
                text=item["text"],
                vector_score=item["vector_score"],
                bm25_score=item["bm25_score"],
                graph_hops=item["graph_hops"],
                rrf_score=item["rrf_score"],
                cross_encoder_score=item["cross_encoder_score"],
                final_rank=rank,
                included=included,
            )
        )

    return RetrievalCompareResponse(
        query=query,
        rrf_k=k,
        vector_cutoff=vector_cutoff,
        cross_encoder_cutoff=cross_encoder_cutoff,
        candidates=candidates,
        total_candidates=len(candidates),
    )
