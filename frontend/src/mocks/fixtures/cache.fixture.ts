export interface CachePointFixture {
  timestamp: string;
  hits: number;
  misses: number;
  wrong_hits: number;
  hit_rate: number;
}

export interface CacheInvalidationFixture {
  id: string;
  timestamp: string;
  trigger_event: string;
  affected_keys_count: number;
  reason: string;
  acl_scope: string;
  keys_purged: string[];
  source_table: string;
}

export const CACHE_SERIES_FIXTURE: CachePointFixture[] = [
  { timestamp: "12:00", hits: 34, misses: 12, wrong_hits: 0, hit_rate: 0.739 },
  { timestamp: "13:00", hits: 45, misses: 15, wrong_hits: 1, hit_rate: 0.75 },
  { timestamp: "14:00", hits: 68, misses: 18, wrong_hits: 1, hit_rate: 0.79 },
  { timestamp: "15:00", hits: 82, misses: 22, wrong_hits: 2, hit_rate: 0.788 },
  { timestamp: "16:00", hits: 96, misses: 19, wrong_hits: 1, hit_rate: 0.835 },
  { timestamp: "17:00", hits: 114, misses: 28, wrong_hits: 2, hit_rate: 0.803 },
  { timestamp: "18:00", hits: 130, misses: 24, wrong_hits: 2, hit_rate: 0.844 },
];

export const INITIAL_INVALIDATIONS_FIXTURE: CacheInvalidationFixture[] = [
  {
    id: "inv-1",
    timestamp: "18:22:40",
    trigger_event: "outbox.event.payment_settled",
    affected_keys_count: 3,
    reason: "Underlying ledger mutated via PostgreSQL CDC",
    acl_scope: "data-platform",
    keys_purged: ["emb:sha256:7f01a...", "emb:sha256:88fa2...", "emb:sha256:09cb1..."],
    source_table: "outbox_events",
  },
  {
    id: "inv-2",
    timestamp: "17:45:12",
    trigger_event: "cdc.qdrant.index_updated",
    affected_keys_count: 2,
    reason: "Document chunk re-indexed",
    acl_scope: "data-platform",
    keys_purged: ["emb:sha256:4a12e...", "emb:sha256:3190b..."],
    source_table: "document_chunks",
  },
  {
    id: "inv-3",
    timestamp: "16:10:04",
    trigger_event: "neo4j.graph.relation_mutated",
    affected_keys_count: 4,
    reason: "Bi-temporal edge retired",
    acl_scope: "data-platform",
    keys_purged: ["emb:sha256:9123b...", "emb:sha256:11a4c...", "emb:sha256:f092a...", "emb:sha256:4421b..."],
    source_table: "graph_edges",
  },
];
