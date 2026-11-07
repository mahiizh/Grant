from datetime import datetime
from typing import Any, TypedDict

from app.core.acl import ACLScope
from app.domain import Evidence


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
    start_time: float
    metadata: dict[str, Any]
    spans: list[dict[str, Any]]
