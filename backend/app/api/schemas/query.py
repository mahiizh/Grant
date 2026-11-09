from datetime import datetime

from pydantic import BaseModel


class QueryRequest(BaseModel):
    """User query payload with optional requested scope and temporal filter."""

    query: str
    scope: str | None = None
    as_of: datetime | None = None
    thread_id: str | None = None


class EvidenceItem(BaseModel):
    """Retrieved evidence passage supporting an answer."""

    chunk_id: str
    doc_id: str
    text: str
    score: float
    retrieval_method: str
    path: list[str] | None = None


class QueryResponse(BaseModel):
    """Synthesized answer accompanied by execution trace and provenance."""

    query: str
    answer: str
    strategy_used: str
    is_cached: bool
    is_abstention: bool
    evidence: list[EvidenceItem]
    path: list[str] | None = None
    cost_usd: float
    latency_ms: float
