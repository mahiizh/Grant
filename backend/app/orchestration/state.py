from typing import Any, Literal, TypedDict

from app.core.acl import ACLScope
from app.domain import Evidence

# Retrieval ablation configurations used by the honest baseline (item 4).
# ``full`` is the production pipeline: router-directed graph traversal plus
# hybrid RRF retrieval plus CrossEncoder reranking. The other three bypass the
# router's retrieval branch and call one retriever directly.
# ``graph_forced`` bypasses the router and always takes the graph branch, then
# uses the same RRF pool and CrossEncoder reranking as ``full``.
RetrievalConfig = Literal["dense", "sparse", "hybrid", "full", "graph_forced"]
AnswerPolicy = Literal["grounded_only", "grounded_plus_web"]
AnswerSourceKind = Literal["docs", "web", "unverified"]
RETRIEVAL_CONFIGS: tuple[RetrievalConfig, ...] = (
    "dense",
    "sparse",
    "hybrid",
    "full",
    "graph_forced",
)


class RAGState(TypedDict, total=False):
    """Execution state passed through the LangGraph orchestration workflow."""

    query: str
    raw_query: str
    rewritten_query: str
    thread_id: str | None
    thread_history: list[dict[str, str]]
    trace_id: str
    acl_scope: ACLScope
    owner_user_id: str | None
    is_admin: bool
    prompt_version: str
    retrieval_config: RetrievalConfig
    answer_policy: AnswerPolicy
    source_kind: AnswerSourceKind
    # Retrieval-only evals skip answer generation; multi-turn rewrites still run.
    retrieval_only: bool
    route: str  # "cache", "vector", "graph", "hybrid", "abstain"
    is_cached: bool
    from_graph_history: bool
    evidence: list[Evidence]
    web_pages: list[dict[str, Any]]
    web_sources: list[dict[str, Any]]
    web_error: str | None
    web_fallback_reason: str | None
    query_id: str | None
    answer_id: str | None
    path: list[str] | None
    answer: str
    is_abstention: bool
    citations_valid: bool
    retry_count: int
    cost_usd: float
    latency_ms: float
    retrieval_latency_ms: float
    stage_timings_ms: dict[str, float]
    start_time: float
    metadata: dict[str, Any]
    spans: list[dict[str, Any]]
