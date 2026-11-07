export interface SpanFixture {
  name: string;
  service: string;
  startMs: number;
  durationMs: number;
  status: "ok" | "miss" | "hit";
  meta: string;
}

export const MOCK_SPANS_FIXTURE: SpanFixture[] = [
  { name: "query.route", service: "langgraph", startMs: 0, durationMs: 14, status: "ok", meta: "hybrid_search (conf 0.91)" },
  { name: "cache.lookup", service: "redis", startMs: 14, durationMs: 6, status: "miss", meta: "cosine_sim 0.64 < threshold 0.92" },
  { name: "retrieve.vector", service: "qdrant", startMs: 20, durationMs: 52, status: "ok", meta: "text-embedding-3-large (3072d)" },
  { name: "retrieve.graph", service: "neo4j", startMs: 22, durationMs: 44, status: "ok", meta: "2-hop bi-temporal BFS" },
  { name: "fuse.rrf", service: "pipeline", startMs: 74, durationMs: 3, status: "ok", meta: "RRF k=60 (14 blended candidates)" },
  { name: "rerank.cross_encoder", service: "cross-encoder", startMs: 78, durationMs: 92, status: "ok", meta: "ms-marco-MiniLM-L-6-v2 (top 5)" },
  { name: "guardrail.evidence_gate", service: "eval_gate", startMs: 170, durationMs: 28, status: "ok", meta: "Faithfulness 0.94 (all claims grounded)" },
  { name: "generate.llm", service: "litellm-proxy", startMs: 198, durationMs: 420, status: "ok", meta: "claude-3-5-sonnet (340 tokens, $0.0031)" },
];
