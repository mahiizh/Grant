export interface ChunkFixture {
  id: number;
  file: string;
  chunkId: string;
  snippet: string;
  highlightedTerm: string;
  score: number;
  rrfRank: number;
  tier: 1 | 2 | 3;
  nodeIds: string[];
}

export const MOCK_CHUNKS_FIXTURE: ChunkFixture[] = [
  {
    id: 1,
    file: "incident-postmortem-2026-03-outbox.md",
    chunkId: "chunk-4",
    snippet:
      "PostgreSQL row-level lock escalation in outbox table blocked asynchronous polling worker, starving downstream CDC replicators for 42 minutes.",
    highlightedTerm: "lock escalation in outbox table",
    score: 0.942,
    rrfRank: 1,
    tier: 1,
    nodeIds: ["outbox", "postgres"],
  },
  {
    id: 2,
    file: "runbook-data-platform-cdc.md",
    chunkId: "chunk-12",
    snippet:
      "Mitigated by Alice Chen (Data Platform lead) via PgBouncer transaction pooling reconfiguration and Qdrant ingestion throttle limits.",
    highlightedTerm: "Alice Chen (Data Platform lead)",
    score: 0.887,
    rrfRank: 2,
    tier: 2,
    nodeIds: ["data_platform", "alice_chen"],
  },
  {
    id: 3,
    file: "arch-dual-write-consistency.md",
    chunkId: "chunk-9",
    snippet:
      "The Transactional Outbox pattern guarantees eventual consistency between PostgreSQL transactions and Neo4j bi-temporal graph writes.",
    highlightedTerm: "Transactional Outbox pattern",
    score: 0.812,
    rrfRank: 3,
    tier: 1,
    nodeIds: ["outbox", "neo4j"],
  },
];
