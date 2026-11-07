export interface RetrievalCandidateFixture {
  chunk_id: string;
  doc_title: string;
  text: string;
  vector_score: number;
  bm25_score: number;
  graph_hops: number;
  rrf_score: number;
  cross_encoder_score: number;
  final_rank: number;
  included: boolean;
  vector_rank: number;
  bm25_rank: number;
  graph_rank: number | null;
  tier: 1 | 2 | 3;
}

export const CANDIDATES_DATA_FIXTURE: RetrievalCandidateFixture[] = [
  {
    chunk_id: "chunk-4",
    doc_title: "incident-postmortem-2026-03-outbox.md#chunk-4",
    text: "PostgreSQL row-level lock escalation in outbox table blocked asynchronous polling worker.",
    vector_score: 0.942,
    bm25_score: 18.4,
    graph_hops: 1,
    rrf_score: 0.0328,
    cross_encoder_score: 0.942,
    final_rank: 1,
    included: true,
    vector_rank: 3,
    bm25_rank: 1,
    graph_rank: 1,
    tier: 1,
  },
  {
    chunk_id: "chunk-12",
    doc_title: "runbook-data-platform-cdc.md#chunk-12",
    text: "Mitigated by Alice Chen (Data Platform lead) via PgBouncer transaction pooling reconfiguration.",
    vector_score: 0.956,
    bm25_score: 12.1,
    graph_hops: 2,
    rrf_score: 0.0315,
    cross_encoder_score: 0.887,
    final_rank: 2,
    included: true,
    vector_rank: 1,
    bm25_rank: 4,
    graph_rank: 2,
    tier: 2,
  },
  {
    chunk_id: "chunk-9",
    doc_title: "arch-dual-write-consistency.md#chunk-9",
    text: "The Transactional Outbox pattern guarantees eventual consistency between PostgreSQL and Neo4j.",
    vector_score: 0.948,
    bm25_score: 9.8,
    graph_hops: 2,
    rrf_score: 0.0298,
    cross_encoder_score: 0.812,
    final_rank: 3,
    included: true,
    vector_rank: 2,
    bm25_rank: 7,
    graph_rank: 3,
    tier: 1,
  },
  {
    chunk_id: "chunk-22",
    doc_title: "incident-postmortem-2026-03-outbox.md#chunk-22",
    text: "Root cause: pool connection starvation prevented CDC polling thread from releasing row locks.",
    vector_score: 0.822,
    bm25_score: 16.2,
    graph_hops: 0,
    rrf_score: 0.0261,
    cross_encoder_score: 0.764,
    final_rank: 4,
    included: true,
    vector_rank: 14,
    bm25_rank: 2,
    graph_rank: null,
    tier: 1,
  },
  {
    chunk_id: "chunk-17",
    doc_title: "runbook-data-platform-cdc.md#chunk-17",
    text: "Qdrant vector collection grant_docs uses HNSW with cosine distance metric and 3072 dimensions.",
    vector_score: 0.915,
    bm25_score: 6.4,
    graph_hops: 3,
    rrf_score: 0.0242,
    cross_encoder_score: 0.728,
    final_rank: 5,
    included: true,
    vector_rank: 4,
    bm25_rank: 11,
    graph_rank: 4,
    tier: 2,
  },
  {
    chunk_id: "chunk-31",
    doc_title: "arch-neo4j-bitemporal.md#chunk-3",
    text: "Valid-time intervals [valid_from, valid_to] ensure point-in-time graph queries remain deterministic.",
    vector_score: 0.884,
    bm25_score: 4.8,
    graph_hops: 3,
    rrf_score: 0.0215,
    cross_encoder_score: 0.691,
    final_rank: 6,
    included: false,
    vector_rank: 6,
    bm25_rank: 15,
    graph_rank: 5,
    tier: 1,
  },
];
