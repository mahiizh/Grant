from pydantic import BaseModel, Field


class CachePoint(BaseModel):
    timestamp: str
    hits: int
    misses: int
    wrong_hits: int
    hit_rate: float


class CacheStatsResponse(BaseModel):
    window: str
    total_requests: int
    overall_hit_rate: float
    wrong_hit_rate: float
    p95_savings_ms: float
    series: list[CachePoint] = Field(default_factory=list)


class CacheInvalidationRecord(BaseModel):
    id: str
    timestamp: str
    trigger_event: str
    affected_keys_count: int
    reason: str
    acl_scope: str


class CacheInvalidationsResponse(BaseModel):
    invalidations: list[CacheInvalidationRecord] = Field(default_factory=list)
    total: int = 0
