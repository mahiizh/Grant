export interface GraphNodeFixture {
  id: string;
  name: string;
  type: string;
  description: string;
  pagerank: number;
  community: number;
  cluster: string;
  valid_from: string;
  valid_to: string | null;
  tx_time: string;
  chunk_hash: string;
  degree: number;
  status: "healthy" | "warning" | "active";
}

export interface GraphLinkFixture {
  source: string;
  target: string;
  label: string;
  tier: number;
  valid_from: string;
  valid_to: string | null;
  tx_time: string;
  chunk_hash: string;
}

export const INITIAL_GRAPH_NODES: GraphNodeFixture[] = [
  { id: "postgres", name: "PostgreSQL 16", type: "database", description: "Primary relational store & transactional outbox table", pagerank: 0.18, community: 1, cluster: "Databases", valid_from: "2026-01-01", valid_to: null, tx_time: "2026-01-01T00:00:00Z", chunk_hash: "sha256:c4f9a012", degree: 8, status: "healthy" },
  { id: "qdrant", name: "Qdrant Vector DB", type: "database", description: "Dense semantic embeddings & sparse BM25 index", pagerank: 0.14, community: 1, cluster: "Databases", valid_from: "2026-01-10", valid_to: null, tx_time: "2026-01-10T04:20:00Z", chunk_hash: "sha256:e1a7b823", degree: 5, status: "healthy" },
  { id: "neo4j", name: "Neo4j 5 Graph", type: "database", description: "Bi-temporal knowledge graph entity-relation store", pagerank: 0.12, community: 1, cluster: "Databases", valid_from: "2026-01-15", valid_to: null, tx_time: "2026-01-15T09:12:00Z", chunk_hash: "sha256:9bf42d10", degree: 4, status: "healthy" },
  { id: "redis", name: "Redis 7 Cache", type: "database", description: "Semantic response cache and token bucket rate limiter", pagerank: 0.11, community: 1, cluster: "Databases", valid_from: "2026-02-01", valid_to: null, tx_time: "2026-02-01T12:00:00Z", chunk_hash: "sha256:33ac419f", degree: 6, status: "warning" },
  { id: "snowflake", name: "Snowflake Lake", type: "database", description: "Analytical data warehouse and historical log sink", pagerank: 0.04, community: 1, cluster: "Databases", valid_from: "2026-02-15", valid_to: null, tx_time: "2026-02-15T15:30:00Z", chunk_hash: "sha256:88fe3910", degree: 2, status: "healthy" },

  { id: "outbox", name: "Transactional Outbox", type: "mechanism", description: "Guarantees dual-write consistency across storage engines", pagerank: 0.15, community: 2, cluster: "Mechanisms", valid_from: "2026-01-05", valid_to: null, tx_time: "2026-01-05T08:00:00Z", chunk_hash: "sha256:a7391b0c", degree: 6, status: "active" },
  { id: "reconciler", name: "Nightly Reconciler", type: "mechanism", description: "Runs 02:00 UTC to heal store drift", pagerank: 0.08, community: 2, cluster: "Mechanisms", valid_from: "2026-02-01", valid_to: null, tx_time: "2026-02-01T02:00:00Z", chunk_hash: "sha256:7b4c20d9", degree: 5, status: "healthy" },
  { id: "dlq", name: "Dead-Letter Queue", type: "mechanism", description: "Holds failed consumer events for inspection & replay", pagerank: 0.06, community: 2, cluster: "Mechanisms", valid_from: "2026-01-10", valid_to: null, tx_time: "2026-01-10T11:45:00Z", chunk_hash: "sha256:1e5509ab", degree: 3, status: "warning" },
  { id: "rrf_fuser", name: "RRF Fusion Engine", type: "mechanism", description: "Reciprocal Rank Fusion (k=60) blending vector and sparse search", pagerank: 0.07, community: 2, cluster: "Mechanisms", valid_from: "2026-02-20", valid_to: null, tx_time: "2026-02-20T17:15:00Z", chunk_hash: "sha256:29f041cb", degree: 3, status: "healthy" },
  { id: "cache_invalidator", name: "Cache Invalidator", type: "mechanism", description: "Subscribes to outbox events to purge stale Redis keys", pagerank: 0.06, community: 2, cluster: "Mechanisms", valid_from: "2026-02-10", valid_to: null, tx_time: "2026-02-10T14:00:00Z", chunk_hash: "sha256:90ca3821", degree: 3, status: "healthy" },
  { id: "event_dispatcher", name: "Event Dispatcher", type: "mechanism", description: "High-throughput async event broker", pagerank: 0.05, community: 2, cluster: "Mechanisms", valid_from: "2026-01-08", valid_to: null, tx_time: "2026-01-08T09:30:00Z", chunk_hash: "sha256:44d21e87", degree: 3, status: "healthy" },

  { id: "alice_chen", name: "Alice Chen", type: "person", description: "Staff Engineer & Tech Lead, Data Platform", pagerank: 0.13, community: 3, cluster: "Leadership", valid_from: "2026-01-01", valid_to: null, tx_time: "2026-01-01T00:00:00Z", chunk_hash: "sha256:f39120de", degree: 4, status: "healthy" },
  { id: "bob_kumar", name: "Bob Kumar", type: "person", description: "Principal Incident Commander & SRE Lead", pagerank: 0.09, community: 3, cluster: "Leadership", valid_from: "2026-01-01", valid_to: null, tx_time: "2026-01-01T00:00:00Z", chunk_hash: "sha256:aa23812f", degree: 4, status: "active" },
  { id: "dave_miller", name: "Dave Miller", type: "person", description: "Engineering Manager, Core Banking", pagerank: 0.07, community: 3, cluster: "Leadership", valid_from: "2026-01-01", valid_to: null, tx_time: "2026-01-01T00:00:00Z", chunk_hash: "sha256:77d291ba", degree: 3, status: "healthy" },
  { id: "elena_rostova", name: "Elena Rostova", type: "person", description: "Staff Distributed Systems Engineer, Payments Lead", pagerank: 0.08, community: 3, cluster: "Leadership", valid_from: "2026-01-01", valid_to: null, tx_time: "2026-01-01T00:00:00Z", chunk_hash: "sha256:c0923e11", degree: 3, status: "healthy" },
  { id: "marcus_vance", name: "Marcus Vance", type: "person", description: "Senior Security Architect", pagerank: 0.06, community: 3, cluster: "Leadership", valid_from: "2026-01-01", valid_to: null, tx_time: "2026-01-01T00:00:00Z", chunk_hash: "sha256:41982bde", degree: 3, status: "healthy" },
  { id: "sophia_lin", name: "Sophia Lin", type: "person", description: "Staff ML Infrastructure Engineer", pagerank: 0.06, community: 3, cluster: "Leadership", valid_from: "2026-02-01", valid_to: null, tx_time: "2026-02-01T10:00:00Z", chunk_hash: "sha256:0a89d2fe", degree: 3, status: "healthy" },

  { id: "data_platform", name: "Data Platform Team", type: "team", description: "Owns PostgreSQL, Qdrant, Neo4j, and the Outbox worker", pagerank: 0.16, community: 4, cluster: "Teams", valid_from: "2026-01-01", valid_to: null, tx_time: "2026-01-01T00:00:00Z", chunk_hash: "sha256:9218ff43", degree: 7, status: "healthy" },
  { id: "sre_team", name: "SRE & Reliability Team", type: "team", description: "Observability pipelines, telemetry, on-call drills", pagerank: 0.08, community: 4, cluster: "Teams", valid_from: "2026-01-01", valid_to: null, tx_time: "2026-01-01T00:00:00Z", chunk_hash: "sha256:4920b12a", degree: 3, status: "healthy" },
  { id: "core_banking_team", name: "Core Banking Team", type: "team", description: "Ledger systems, exchange rates, currency consistency", pagerank: 0.10, community: 4, cluster: "Teams", valid_from: "2026-01-01", valid_to: null, tx_time: "2026-01-01T00:00:00Z", chunk_hash: "sha256:00192e44", degree: 5, status: "warning" },
  { id: "payments_team", name: "Payments Team", type: "team", description: "Checkout pipelines, payment gateways, fraud intercept", pagerank: 0.09, community: 4, cluster: "Teams", valid_from: "2026-01-01", valid_to: null, tx_time: "2026-01-01T00:00:00Z", chunk_hash: "sha256:1938fe10", degree: 4, status: "healthy" },
  { id: "security_team", name: "Security & Compliance", type: "team", description: "Access control lists, audit logs, key vault management", pagerank: 0.08, community: 4, cluster: "Teams", valid_from: "2026-01-01", valid_to: null, tx_time: "2026-01-01T00:00:00Z", chunk_hash: "sha256:59102cba", degree: 4, status: "healthy" },

  { id: "payment_gw", name: "PaymentGateway", type: "service", description: "Credit card processing and external merchant integration", pagerank: 0.08, community: 5, cluster: "Services", valid_from: "2026-01-10", valid_to: null, tx_time: "2026-01-10T12:00:00Z", chunk_hash: "sha256:7a2130e9", degree: 6, status: "warning" },
  { id: "core_banking", name: "CoreBanking Service", type: "service", description: "Authoritative account balance & transaction ledger v2.4.1", pagerank: 0.11, community: 5, cluster: "Services", valid_from: "2026-01-05", valid_to: null, tx_time: "2026-01-05T08:00:00Z", chunk_hash: "sha256:92147ae0", degree: 4, status: "healthy" },
  { id: "fraud_scorer", name: "FraudScorer Proxy", type: "service", description: "Real-time risk scoring for transactional checkout", pagerank: 0.05, community: 5, cluster: "Services", valid_from: "2026-02-15", valid_to: null, tx_time: "2026-02-15T10:00:00Z", chunk_hash: "sha256:a90231cf", degree: 3, status: "healthy" },
  { id: "exchange_engine", name: "ExchangeRate Engine", type: "service", description: "Live currency conversion cache sync", pagerank: 0.06, community: 5, cluster: "Services", valid_from: "2026-01-20", valid_to: null, tx_time: "2026-01-20T14:30:00Z", chunk_hash: "sha256:5f839201", degree: 4, status: "warning" },
  { id: "ledger_svc", name: "DoubleEntry Ledger", type: "service", description: "Immutable balance journals and reconciliation", pagerank: 0.07, community: 5, cluster: "Services", valid_from: "2026-01-01", valid_to: null, tx_time: "2026-01-01T00:00:00Z", chunk_hash: "sha256:b218903c", degree: 3, status: "healthy" },
  { id: "auth_proxy", name: "Auth & ACL Gateway", type: "service", description: "JWT validation, role checking, tenant sandboxing", pagerank: 0.08, community: 5, cluster: "Services", valid_from: "2026-01-01", valid_to: null, tx_time: "2026-01-01T00:00:00Z", chunk_hash: "sha256:8e9201bd", degree: 4, status: "healthy" },
  { id: "otel_collector", name: "OpenTelemetry Collector", type: "service", description: "Aggregates gen_ai.* spans and distributed traces", pagerank: 0.06, community: 5, cluster: "Services", valid_from: "2026-02-01", valid_to: null, tx_time: "2026-02-01T09:00:00Z", chunk_hash: "sha256:4421980f", degree: 3, status: "healthy" },
  { id: "checkout_pipeline", name: "Checkout Pipeline", type: "service", description: "Customer shopping checkout orchestration", pagerank: 0.07, community: 5, cluster: "Services", valid_from: "2026-01-15", valid_to: null, tx_time: "2026-01-15T11:00:00Z", chunk_hash: "sha256:d9182301", degree: 4, status: "healthy" },
  { id: "notification_svc", name: "Notification Hub", type: "service", description: "Customer webhook and SMS dispatch service", pagerank: 0.04, community: 5, cluster: "Services", valid_from: "2026-02-25", valid_to: null, tx_time: "2026-02-25T16:00:00Z", chunk_hash: "sha256:3f9012a8", degree: 2, status: "healthy" },
  { id: "embedding_worker", name: "Embedding Worker", type: "service", description: "Generates 768-dim semantic vectors on document ingestion", pagerank: 0.06, community: 5, cluster: "Services", valid_from: "2026-03-01", valid_to: null, tx_time: "2026-03-01T08:30:00Z", chunk_hash: "sha256:6c2019ea", degree: 3, status: "healthy" },
  { id: "reconcile_daemon", name: "Store Reconciliation Daemon", type: "service", description: "Verifies database index parity", pagerank: 0.05, community: 5, cluster: "Services", valid_from: "2026-03-05", valid_to: null, tx_time: "2026-03-05T12:00:00Z", chunk_hash: "sha256:a18390cb", degree: 2, status: "healthy" },
  { id: "search_proxy", name: "Hybrid Search Proxy", type: "service", description: "Exposes hybrid vector + BM25 query APIs", pagerank: 0.07, community: 5, cluster: "Services", valid_from: "2026-03-10", valid_to: null, tx_time: "2026-03-10T14:00:00Z", chunk_hash: "sha256:2039ab1e", degree: 4, status: "healthy" },
  { id: "model_gateway_svc", name: "Model Gateway", type: "service", description: "LiteLLM provider proxy with token cost cap enforcement", pagerank: 0.08, community: 5, cluster: "Services", valid_from: "2026-03-15", valid_to: null, tx_time: "2026-03-15T18:00:00Z", chunk_hash: "sha256:991823ab", degree: 4, status: "healthy" },
  { id: "audit_logger", name: "Audit Logger", type: "service", description: "Tamper-evident system activity logger", pagerank: 0.05, community: 5, cluster: "Services", valid_from: "2026-01-01", valid_to: null, tx_time: "2026-01-01T00:00:00Z", chunk_hash: "sha256:3081920b", degree: 3, status: "healthy" },
];

export const INITIAL_GRAPH_LINKS: GraphLinkFixture[] = [
  { source: "outbox", target: "postgres", label: "STAGED_IN", tier: 1, valid_from: "2026-01-05", valid_to: null, tx_time: "2026-01-05T08:00:00Z", chunk_hash: "sha256:a7391b0c" },
  { source: "postgres", target: "data_platform", label: "OWNED_BY", tier: 1, valid_from: "2026-01-01", valid_to: null, tx_time: "2026-01-01T00:00:00Z", chunk_hash: "sha256:9218ff43" },
  { source: "data_platform", target: "alice_chen", label: "LED_BY", tier: 1, valid_from: "2026-01-01", valid_to: null, tx_time: "2026-01-01T00:00:00Z", chunk_hash: "sha256:f39120de" },
  { source: "qdrant", target: "data_platform", label: "OWNED_BY", tier: 1, valid_from: "2026-01-10", valid_to: null, tx_time: "2026-01-10T04:20:00Z", chunk_hash: "sha256:e1a7b823" },
  { source: "neo4j", target: "data_platform", label: "OWNED_BY", tier: 1, valid_from: "2026-01-15", valid_to: null, tx_time: "2026-01-15T09:12:00Z", chunk_hash: "sha256:9bf42d10" },
  { source: "redis", target: "data_platform", label: "MAINTAINED_BY", tier: 1, valid_from: "2026-02-01", valid_to: null, tx_time: "2026-02-01T12:00:00Z", chunk_hash: "sha256:33ac419f" },
  { source: "snowflake", target: "data_platform", label: "INGESTED_BY", tier: 2, valid_from: "2026-02-15", valid_to: null, tx_time: "2026-02-15T15:30:00Z", chunk_hash: "sha256:88fe3910" },
  { source: "embedding_worker", target: "qdrant", label: "WRITES_TO", tier: 2, valid_from: "2026-03-01", valid_to: null, tx_time: "2026-03-01T08:30:00Z", chunk_hash: "sha256:6c2019ea" },
  { source: "embedding_worker", target: "outbox", label: "CONSUMES_FROM", tier: 2, valid_from: "2026-03-01", valid_to: null, tx_time: "2026-03-01T08:30:00Z", chunk_hash: "sha256:6c2019ea" },
  { source: "search_proxy", target: "qdrant", label: "QUERIES_VECTOR", tier: 1, valid_from: "2026-03-10", valid_to: null, tx_time: "2026-03-10T14:00:00Z", chunk_hash: "sha256:2039ab1e" },
  { source: "search_proxy", target: "rrf_fuser", label: "USES_RRF", tier: 1, valid_from: "2026-03-10", valid_to: null, tx_time: "2026-03-10T14:00:00Z", chunk_hash: "sha256:2039ab1e" },
  { source: "rrf_fuser", target: "postgres", label: "FETCHES_TEXT", tier: 1, valid_from: "2026-02-20", valid_to: null, tx_time: "2026-02-20T17:15:00Z", chunk_hash: "sha256:29f041cb" },
  { source: "reconciler", target: "postgres", label: "AUDITS_SOURCE", tier: 1, valid_from: "2026-02-01", valid_to: null, tx_time: "2026-02-01T02:00:00Z", chunk_hash: "sha256:7b4c20d9" },
  { source: "reconciler", target: "qdrant", label: "REPAIRS_INDEX", tier: 1, valid_from: "2026-02-01", valid_to: null, tx_time: "2026-02-01T02:00:00Z", chunk_hash: "sha256:7b4c20d9" },
  { source: "reconciler", target: "neo4j", label: "REPAIRS_GRAPH", tier: 1, valid_from: "2026-02-01", valid_to: null, tx_time: "2026-02-01T02:00:00Z", chunk_hash: "sha256:7b4c20d9" },
  { source: "reconcile_daemon", target: "reconciler", label: "EXECUTES", tier: 2, valid_from: "2026-03-05", valid_to: null, tx_time: "2026-03-05T12:00:00Z", chunk_hash: "sha256:a18390cb" },
  { source: "outbox", target: "dlq", label: "ROUTES_FAILED", tier: 1, valid_from: "2026-01-10", valid_to: null, tx_time: "2026-01-10T11:45:00Z", chunk_hash: "sha256:1e5509ab" },
  { source: "dlq", target: "alice_chen", label: "ASSIGNED_REMEDIATION", tier: 3, valid_from: "2026-03-15", valid_to: null, tx_time: "2026-03-15T00:00:00Z", chunk_hash: "sha256:f39120de" },
  { source: "cache_invalidator", target: "redis", label: "PURGES_KEYS", tier: 1, valid_from: "2026-02-10", valid_to: null, tx_time: "2026-02-10T14:00:00Z", chunk_hash: "sha256:90ca3821" },
  { source: "cache_invalidator", target: "outbox", label: "TRIGGERS_FROM", tier: 1, valid_from: "2026-02-10", valid_to: null, tx_time: "2026-02-10T14:00:00Z", chunk_hash: "sha256:90ca3821" },
  { source: "sre_team", target: "bob_kumar", label: "LED_BY", tier: 1, valid_from: "2026-01-01", valid_to: null, tx_time: "2026-01-01T00:00:00Z", chunk_hash: "sha256:aa23812f" },
  { source: "bob_kumar", target: "otel_collector", label: "CONFIGURES", tier: 1, valid_from: "2026-02-01", valid_to: null, tx_time: "2026-02-01T09:00:00Z", chunk_hash: "sha256:aa23812f" },
  { source: "otel_collector", target: "sre_team", label: "MONITORED_BY", tier: 2, valid_from: "2026-02-01", valid_to: null, tx_time: "2026-02-01T09:00:00Z", chunk_hash: "sha256:4421980f" },
  { source: "bob_kumar", target: "payment_gw", label: "TRIAGED_INCIDENT", tier: 3, valid_from: "2026-04-01", valid_to: null, tx_time: "2026-04-01T00:00:00Z", chunk_hash: "sha256:aa23812f" },
  { source: "payments_team", target: "elena_rostova", label: "LED_BY", tier: 1, valid_from: "2026-01-01", valid_to: null, tx_time: "2026-01-01T00:00:00Z", chunk_hash: "sha256:c0923e11" },
  { source: "payment_gw", target: "payments_team", label: "OWNED_BY", tier: 1, valid_from: "2026-01-10", valid_to: null, tx_time: "2026-01-10T12:00:00Z", chunk_hash: "sha256:7a2130e9" },
  { source: "checkout_pipeline", target: "payment_gw", label: "INVOKES", tier: 1, valid_from: "2026-01-15", valid_to: null, tx_time: "2026-01-15T11:00:00Z", chunk_hash: "sha256:d9182301" },
  { source: "checkout_pipeline", target: "payments_team", label: "OWNED_BY", tier: 2, valid_from: "2026-01-15", valid_to: null, tx_time: "2026-01-15T11:00:00Z", chunk_hash: "sha256:d9182301" },
  { source: "payment_gw", target: "fraud_scorer", label: "CHECKS_RISK", tier: 1, valid_from: "2026-02-15", valid_to: null, tx_time: "2026-02-15T10:00:00Z", chunk_hash: "sha256:a90231cf" },
  { source: "fraud_scorer", target: "payments_team", label: "OWNED_BY", tier: 2, valid_from: "2026-02-15", valid_to: null, tx_time: "2026-02-15T10:00:00Z", chunk_hash: "sha256:a90231cf" },
  { source: "payment_gw", target: "redis", label: "READS_CACHE", tier: 3, valid_from: "2026-02-20", valid_to: null, tx_time: "2026-02-20T00:00:00Z", chunk_hash: "sha256:33ac419f" },
  { source: "core_banking_team", target: "dave_miller", label: "LED_BY", tier: 1, valid_from: "2026-01-01", valid_to: null, tx_time: "2026-01-01T00:00:00Z", chunk_hash: "sha256:77d291ba" },
  { source: "core_banking", target: "core_banking_team", label: "OWNED_BY", tier: 1, valid_from: "2026-01-05", valid_to: null, tx_time: "2026-01-05T08:00:00Z", chunk_hash: "sha256:92147ae0" },
  { source: "exchange_engine", target: "core_banking_team", label: "OWNED_BY", tier: 1, valid_from: "2026-01-20", valid_to: null, tx_time: "2026-01-20T14:30:00Z", chunk_hash: "sha256:5f839201" },
  { source: "exchange_engine", target: "postgres", label: "PERSISTS_RATES", tier: 1, valid_from: "2026-01-20", valid_to: null, tx_time: "2026-01-20T14:30:00Z", chunk_hash: "sha256:5f839201" },
  { source: "exchange_engine", target: "redis", label: "UPDATES_CACHE", tier: 2, valid_from: "2026-02-01", valid_to: null, tx_time: "2026-02-01T00:00:00Z", chunk_hash: "sha256:33ac419f" },
  { source: "ledger_svc", target: "core_banking_team", label: "OWNED_BY", tier: 1, valid_from: "2026-01-01", valid_to: null, tx_time: "2026-01-01T00:00:00Z", chunk_hash: "sha256:b218903c" },
  { source: "ledger_svc", target: "postgres", label: "WRITES_TRANSACTIONS", tier: 1, valid_from: "2026-01-01", valid_to: null, tx_time: "2026-01-01T00:00:00Z", chunk_hash: "sha256:b218903c" },
  { source: "core_banking", target: "exchange_engine", label: "DEPENDS_ON", tier: 1, valid_from: "2026-01-20", valid_to: null, tx_time: "2026-01-20T14:30:00Z", chunk_hash: "sha256:5f839201" },
  { source: "payment_gw", target: "core_banking", label: "SETTLES_VIA", tier: 1, valid_from: "2026-01-10", valid_to: null, tx_time: "2026-01-10T12:00:00Z", chunk_hash: "sha256:7a2130e9" },
  { source: "security_team", target: "marcus_vance", label: "LED_BY", tier: 1, valid_from: "2026-01-01", valid_to: null, tx_time: "2026-01-01T00:00:00Z", chunk_hash: "sha256:41982bde" },
  { source: "auth_proxy", target: "security_team", label: "OWNED_BY", tier: 1, valid_from: "2026-01-01", valid_to: null, tx_time: "2026-01-01T00:00:00Z", chunk_hash: "sha256:8e9201bd" },
  { source: "auth_proxy", target: "redis", label: "CHECKS_TOKENS", tier: 1, valid_from: "2026-02-01", valid_to: null, tx_time: "2026-02-01T00:00:00Z", chunk_hash: "sha256:33ac419f" },
  { source: "checkout_pipeline", target: "auth_proxy", label: "AUTHENTICATES_VIA", tier: 1, valid_from: "2026-01-15", valid_to: null, tx_time: "2026-01-15T11:00:00Z", chunk_hash: "sha256:d9182301" },
  { source: "audit_logger", target: "security_team", label: "AUDITED_BY", tier: 1, valid_from: "2026-01-01", valid_to: null, tx_time: "2026-01-01T00:00:00Z", chunk_hash: "sha256:3081920b" },
  { source: "audit_logger", target: "postgres", label: "ARCHIVES_TO", tier: 1, valid_from: "2026-01-01", valid_to: null, tx_time: "2026-01-01T00:00:00Z", chunk_hash: "sha256:3081920b" },
  { source: "sophia_lin", target: "data_platform", label: "CONTRIBUTES_TO", tier: 2, valid_from: "2026-02-01", valid_to: null, tx_time: "2026-02-01T10:00:00Z", chunk_hash: "sha256:0a89d2fe" },
  { source: "model_gateway_svc", target: "sophia_lin", label: "DESIGNED_BY", tier: 2, valid_from: "2026-03-15", valid_to: null, tx_time: "2026-03-15T18:00:00Z", chunk_hash: "sha256:991823ab" },
  { source: "model_gateway_svc", target: "search_proxy", label: "AUGMENTS_PROMPT", tier: 1, valid_from: "2026-03-15", valid_to: null, tx_time: "2026-03-15T18:00:00Z", chunk_hash: "sha256:991823ab" },
  { source: "model_gateway_svc", target: "redis", label: "CHECKS_SEMANTIC_CACHE", tier: 1, valid_from: "2026-03-15", valid_to: null, tx_time: "2026-03-15T18:00:00Z", chunk_hash: "sha256:991823ab" },
  { source: "notification_svc", target: "event_dispatcher", label: "SUBSCRIBES_TO", tier: 2, valid_from: "2026-02-25", valid_to: null, tx_time: "2026-02-25T16:00:00Z", chunk_hash: "sha256:3f9012a8" },
  { source: "event_dispatcher", target: "data_platform", label: "OWNED_BY", tier: 1, valid_from: "2026-01-08", valid_to: null, tx_time: "2026-01-08T09:30:00Z", chunk_hash: "sha256:44d21e87" },
];
