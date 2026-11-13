from datetime import datetime
from typing import Any, Literal, TypedDict

from app.core.acl import ACLScope
from app.domain import Evidence

# Retrieval ablation configurations used by the honest baseline (item 4).
# ``full`` is the production pipeline: router-directed graph traversal plus
# hybrid RRF retrieval plus CrossEncoder reranking. The other three bypass the
# router's retrieval branch and call one retriever directly.
RetrievalConfig = Literal["dense", "sparse", "hybrid", "full"]
RETRIEVAL_CONFIGS: tuple[RetrievalConfig, ...] = ("dense", "sparse", "hybrid", "full")


class RAGState(TypedDict, total=False):
    """Execution state passed through the LangGraph orchestration workflow."""

    query: str
    raw_query: str
    rewritten_query: str
    thread_id: str | None
    thread_history: list[dict[str, str]]
    trace_id: str
    acl_scope: ACLScope
    as_of_time: datetime | None
    prompt_version: str
    retrieval_config: RetrievalConfig
    route: str  # "cache", "vector", "graph", "hybrid", "abstain"
    is_cached: bool
    evidence: list[Evidence]
    path: list[str] | None
    answer: str
    is_abstention: bool
    citations_valid: bool
    retry_count: int
    cost_usd: float
    latency_ms: float
    retrieval_latency_ms: float
    start_time: float
    metadata: dict[str, Any]
    spans: list[dict[str, Any]]
