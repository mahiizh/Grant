from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class CitationItem(BaseModel):
    chunk_id: str
    doc_id: str
    text: str
    score: float
    retrieval_method: str
    path: list[str] | None = None


class PipelineStageItem(BaseModel):
    id: str
    label: str
    status: str  # "completed" | "in_progress" | "pending" | "failed"
    duration_ms: float | None = None
    detail: str | None = None


class MessageGeneration(BaseModel):
    generation_id: str
    content: str
    rewritten_query: str | None = None
    route: str | None = None
    cache_status: str | None = None
    latency_ms: float | None = None
    cost_usd: float | None = None
    tokens: int | None = None
    trace_id: str | None = None
    citations: list[CitationItem] = []
    source_kind: Literal["docs", "web", "unverified"] = "docs"
    web_sources: list[dict[str, Any]] = Field(default_factory=list)
    query_id: str | None = None
    answer_id: str | None = None
    created_at: datetime


class MessageItem(BaseModel):
    message_id: str
    thread_id: str
    role: str  # "user" | "assistant" | "system"
    content: str
    raw_query: str | None = None
    rewritten_query: str | None = None
    route: str | None = None
    cache_status: str | None = None
    latency_ms: float | None = None
    cost_usd: float | None = None
    tokens: int | None = None
    trace_id: str | None = None
    citations: list[CitationItem] = []
    pipeline_stages: list[PipelineStageItem] = []
    subgraph_nodes: list[str] = []
    feedback: str | None = None  # "up" | "down"
    feedback_note: str | None = None
    generations: list[MessageGeneration] = []
    source_kind: Literal["docs", "web", "unverified"] = "docs"
    web_sources: list[dict[str, Any]] = Field(default_factory=list)
    query_id: str | None = None
    answer_id: str | None = None
    created_at: datetime


class ThreadSummary(BaseModel):
    thread_id: str
    title: str
    acl_scope: str
    as_of_date: str | None = None
    created_at: datetime
    updated_at: datetime
    message_count: int = 0
    preview: str | None = None


class ThreadDetail(BaseModel):
    thread_id: str
    title: str
    acl_scope: str
    as_of_date: str | None = None
    created_at: datetime
    updated_at: datetime
    messages: list[MessageItem] = []


class CreateThreadRequest(BaseModel):
    title: str | None = None
    acl_scope: str = "data-platform"
    as_of_date: str | None = None


class UpdateThreadRequest(BaseModel):
    title: str | None = None
    acl_scope: str | None = None
    as_of_date: str | None = None


class SendMessageRequest(BaseModel):
    content: str = Field(..., min_length=1)
    acl_scope: str | None = None
    as_of_date: str | None = None
    retrieval_mode: str | None = None  # "hybrid" | "vector" | "graph"
    use_cache: bool = True
    use_rerank: bool = True
    answer_policy: Literal["grounded_only", "grounded_plus_web"] = "grounded_plus_web"


class FeedbackRequest(BaseModel):
    feedback: str = Field(..., pattern="^(up|down)$")
    note: str | None = None


class AddToGoldenRequest(BaseModel):
    category: str = "multi_turn"
    expected_answer: str | None = None
