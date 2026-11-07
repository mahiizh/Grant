from pydantic import BaseModel, Field


class RetrievalCandidate(BaseModel):
    chunk_id: str
    doc_title: str
    text: str
    vector_score: float
    bm25_score: float
    graph_hops: int
    rrf_score: float
    cross_encoder_score: float
    final_rank: int
    included: bool


class RetrievalCompareResponse(BaseModel):
    query: str
    rrf_k: int
    vector_cutoff: float
    cross_encoder_cutoff: float
    candidates: list[RetrievalCandidate] = Field(default_factory=list)
    total_candidates: int = 0
