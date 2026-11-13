from pydantic import BaseModel


class GuardrailsMetricsResponse(BaseModel):
    prompt_injection_attempts: int
    pii_redactions: int
    faithfulness_gate_rejections: int
    hallucination_eval_score: float
    pass_rate: float


class OverviewMetricsResponse(BaseModel):
    docs_indexed: int
    chunks_indexed: int
    entities_indexed: int
    relations_indexed: int
    # ``None`` means the pipeline does not measure the value. Clients must render
    # an empty state instead of treating it as zero.
    golden_set_accuracy: float | None = None
    p95_latency_ms: int | None = None
    cache_hit_rate: float | None = None
    cache_wrong_hit_rate: float | None = None
    cost_per_correct_answer_usd: float | None = None
    unverified_facts_pending: int
