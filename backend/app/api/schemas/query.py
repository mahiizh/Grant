from typing import Any, Literal

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    """User query payload with an optional shared scope and answer policy."""

    query: str
    scope: str | None = None
    thread_id: str | None = None
    answer_policy: Literal["grounded_only", "grounded_plus_web"] = "grounded_plus_web"


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
    source_kind: Literal["docs", "web", "unverified"] = "docs"
    web_sources: list[dict[str, Any]] = Field(default_factory=list)
    query_id: str | None = None
    answer_id: str | None = None
    stage_timings_ms: dict[str, float] = Field(default_factory=dict)
