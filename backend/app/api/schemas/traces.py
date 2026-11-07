from typing import Any

from pydantic import BaseModel, Field


class SpanRecord(BaseModel):
    name: str
    service: str
    start_ms: int
    duration_ms: int
    status: str = "ok"
    meta: str = ""


class TraceSummary(BaseModel):
    id: str
    query: str
    route: str
    latency_ms: int
    status: str
    timestamp: str
    tokens: int
    cost_usd: float
    cached: bool = False
    error_message: str | None = None


class TracesResponse(BaseModel):
    traces: list[TraceSummary]
    total: int


class TraceDetail(BaseModel):
    id: str
    query: str
    route: str
    latency_ms: int
    status: str
    timestamp: str
    tokens: int
    cost_usd: float
    spans: list[SpanRecord] = Field(default_factory=list)
    inputs: dict[str, Any] = Field(default_factory=dict)
    retrieved_chunk_ids: list[str] = Field(default_factory=list)
    answer: str = ""
