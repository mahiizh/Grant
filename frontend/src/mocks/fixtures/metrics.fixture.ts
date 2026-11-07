export const INITIAL_OVERVIEW_METRICS = {
  docs_indexed: 4,
  chunks_indexed: 47,
  entities_indexed: 36,
  relations_indexed: 54,
  golden_set_accuracy: 0.942,
  p95_latency_ms: 618,
  cache_hit_rate: 0.842,
  cache_wrong_hit_rate: 0.008,
  cost_per_correct_answer_usd: 0.0031,
  unverified_facts_pending: 0,
};

export const INITIAL_GUARDRAILS_METRICS = {
  prompt_injection_attempts: 14,
  pii_redactions: 9,
  faithfulness_gate_rejections: 2,
  hallucination_eval_score: 0.965,
  pass_rate: 0.985,
};
