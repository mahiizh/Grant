export interface ExperimentRunFixture {
  id: string;
  name: string;
  status: string;
  variant_a_route: string;
  variant_b_route: string;
  traffic_split: number;
  variant_a_accuracy: number;
  variant_b_accuracy: number;
  p95_latency_ms: number;
  cost_per_1k: number;
  total_queries: number;
}

export const INITIAL_EXPERIMENTS_FIXTURE: ExperimentRunFixture[] = [
  {
    id: "exp-001",
    name: "Vector Baseline vs Hybrid RRF Blending",
    status: "active",
    variant_a_route: "vector_only",
    variant_b_route: "hybrid_rrf",
    traffic_split: 50,
    variant_a_accuracy: 0.625,
    variant_b_accuracy: 1.0,
    p95_latency_ms: 618,
    cost_per_1k: 2.74,
    total_queries: 1840,
  },
  {
    id: "exp-002",
    name: "BM25 Sparse Only vs Bi-Temporal Neo4j BFS",
    status: "completed",
    variant_a_route: "bm25_only",
    variant_b_route: "temporal_cypher",
    traffic_split: 0,
    variant_a_accuracy: 0.512,
    variant_b_accuracy: 0.945,
    p95_latency_ms: 310,
    cost_per_1k: 1.85,
    total_queries: 3420,
  },
];
