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
    golden_set_accuracy: float
    p95_latency_ms: int
    cache_hit_rate: float
    cache_wrong_hit_rate: float
    cost_per_correct_answer_usd: float
    unverified_facts_pending: int
