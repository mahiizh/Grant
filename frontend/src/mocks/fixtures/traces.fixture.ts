export interface TraceSpanFixture {
  id: string;
  name: string;
  lane: string;
  startMs: number;
  durationMs: number;
  status: "ok" | "error" | "miss" | "hit";
  attributes: Record<string, any>;
  input?: string;
  output?: string;
}

export interface TraceRecordFixture {
  id: string;
  query: string;
  timestamp: string;
  totalDurationMs: number;
  totalTokens: number;
  costUsd: number;
  route: string;
  cacheStatus: "hit" | "miss";
  status: "success" | "error" | "abstained";
  spans: TraceSpanFixture[];
}

export const TRACES_DATA_FIXTURE: TraceRecordFixture[] = [
  {
    id: "tr-8f92a10b",
    query: "Why did the outbox service fail to sync state to PostgreSQL for Alice Chen's team?",
    timestamp: "2026-04-12 18:24:02",
    totalDurationMs: 618,
    totalTokens: 462,
    costUsd: 0.0031,
    route: "hybrid_search",
    cacheStatus: "miss",
    status: "success",
    spans: [
      {
        id: "sp-1",
        name: "orchestrator.route",
        lane: "langgraph.orchestrator",
        startMs: 0,
        durationMs: 14,
        status: "ok",
        attributes: {
          "route.strategy": "hybrid_search",
          "route.confidence": 0.91,
          "langgraph.node": "route_step",
        },
        input: '{"query": "Why did the outbox service fail to sync state to PostgreSQL for Alice Chen\'s team?"}',
        output: '{"route": "hybrid_search", "requires_temporal": false, "entity_hints": ["outbox", "postgres", "alice_chen"]}',
      },
      {
        id: "sp-2",
        name: "cache.check",
        lane: "cache.redis",
        startMs: 14,
        durationMs: 6,
        status: "miss",
        attributes: {
          "db.system": "redis",
          "cache.cosine_sim": 0.642,
          "cache.threshold": 0.92,
          "cache.hit": false,
        },
        input: '{"embedding_key": "emb:sha256:88fa290..."}',
        output: '{"status": "MISS", "top_cached_entry_sim": 0.642}',
      },
      {
        id: "sp-3",
        name: "vector.search",
        lane: "retrieval.vector",
        startMs: 20,
        durationMs: 52,
        status: "ok",
        attributes: {
          "db.system": "qdrant",
          "qdrant.collection": "grant_docs",
          "qdrant.limit": 20,
          "qdrant.ef_search": 128,
        },
        input: '{"vector": [0.012, -0.045, ...], "limit": 20, "score_threshold": 0.75}',
        output: '{"returned_points": 14, "top_score": 0.942, "source": "incident-postmortem-2026-03-outbox.md"}',
      },
      {
        id: "sp-4",
        name: "graph.traversal",
        lane: "retrieval.graph",
        startMs: 22,
        durationMs: 44,
        status: "ok",
        attributes: {
          "db.system": "neo4j",
          "neo4j.hops": 2,
          "neo4j.valid_from": "2026-04-12",
        },
        input: 'MATCH (m:Mechanism {id:"outbox"})-[r*1..2]-(n) WHERE n.valid_from <= "2026-04-12" RETURN m, r, n LIMIT 25',
        output: '{"nodes_found": 8, "edges_found": 12, "hubs": ["postgres", "data_platform"]}',
      },
      {
        id: "sp-5",
        name: "ranking.rrf_fuse",
        lane: "ranking.rrf",
        startMs: 74,
        durationMs: 3,
        status: "ok",
        attributes: {
          "rrf.k": 60,
          "rrf.inputs": "qdrant_vector + neo4j_graph",
          "rrf.candidates": 22,
        },
        input: '{"vector_ranks": 14, "graph_ranks": 8}',
        output: '{"fused_ranked_results": 14, "top_id": "chunk-4"}',
      },
      {
        id: "sp-6",
        name: "ranking.cross_encoder",
        lane: "ranking.cross_encoder",
        startMs: 78,
        durationMs: 92,
        status: "ok",
        attributes: {
          "model.name": "ms-marco-MiniLM-L-6-v2",
          "top_k_retained": 5,
        },
        input: '{"pairs": 14, "batch_size": 16}',
        output: '{"reranked_top_k": 5, "top_score": 0.942}',
      },
      {
        id: "sp-7",
        name: "guardrails.evidence_gate",
        lane: "eval.guardrails",
        startMs: 170,
        durationMs: 28,
        status: "ok",
        attributes: {
          "eval.metric": "faithfulness",
          "eval.score": 0.94,
          "eval.decision": "PASSED",
        },
        input: '{"candidate_claims": 3, "retrieved_chunks": 5}',
        output: '{"claims_verified": 3, "ungrounded_claims_dropped": 0, "pass": true}',
      },
      {
        id: "sp-8",
        name: "gen_ai.generate",
        lane: "gen_ai.llm",
        startMs: 198,
        durationMs: 420,
        status: "ok",
        attributes: {
          "gen_ai.system": "anthropic",
          "gen_ai.request.model": "claude-3-5-sonnet",
          "gen_ai.usage.prompt_tokens": 122,
          "gen_ai.usage.completion_tokens": 340,
          "gen_ai.usage.cost_usd": 0.0031,
        },
        input: 'System: You are Grant Lab Assistant with strict citation grounding...\nUser: Why did the outbox service fail to sync state to PostgreSQL for Alice Chen\'s team?',
        output: 'The transactional outbox service experienced replication stalls due to row-level lock escalation on PostgreSQL table outbox_events [1]...',
      },
    ],
  },
  {
    id: "tr-3c419e02",
    query: "What databases and services depend on the Qdrant vector index when processing core-banking events?",
    timestamp: "2026-04-12 17:50:11",
    totalDurationMs: 485,
    totalTokens: 380,
    costUsd: 0.0024,
    route: "graph_traversal",
    cacheStatus: "miss",
    status: "success",
    spans: [
      {
        id: "sp-201",
        name: "orchestrator.route",
        lane: "langgraph.orchestrator",
        startMs: 0,
        durationMs: 12,
        status: "ok",
        attributes: { "route.strategy": "graph_traversal", "route.confidence": 0.95 },
      },
      {
        id: "sp-202",
        name: "cache.check",
        lane: "cache.redis",
        startMs: 12,
        durationMs: 4,
        status: "miss",
        attributes: { "db.system": "redis", "cache.hit": false },
      },
      {
        id: "sp-203",
        name: "graph.traversal",
        lane: "retrieval.graph",
        startMs: 16,
        durationMs: 68,
        status: "ok",
        attributes: { "db.system": "neo4j", "neo4j.hops": 3 },
      },
      {
        id: "sp-204",
        name: "gen_ai.generate",
        lane: "gen_ai.llm",
        startMs: 85,
        durationMs: 400,
        status: "ok",
        attributes: { "gen_ai.request.model": "claude-3-5-sonnet", "gen_ai.usage.completion_tokens": 280 },
      },
    ],
  },
  {
    id: "tr-7b0198ca",
    query: "Which SLA contracts were active on 2026-03-01 before the schema migration?",
    timestamp: "2026-04-12 16:15:30",
    totalDurationMs: 310,
    totalTokens: 290,
    costUsd: 0.0018,
    route: "temporal_cypher",
    cacheStatus: "miss",
    status: "success",
    spans: [
      {
        id: "sp-301",
        name: "orchestrator.route",
        lane: "langgraph.orchestrator",
        startMs: 0,
        durationMs: 15,
        status: "ok",
        attributes: { "route.strategy": "temporal_cypher" },
      },
      {
        id: "sp-302",
        name: "graph.temporal_point_in_time",
        lane: "retrieval.graph",
        startMs: 15,
        durationMs: 42,
        status: "ok",
        attributes: { "neo4j.point_in_time": "2026-03-01" },
      },
      {
        id: "sp-303",
        name: "gen_ai.generate",
        lane: "gen_ai.llm",
        startMs: 57,
        durationMs: 253,
        status: "ok",
        attributes: { "gen_ai.request.model": "claude-3-5-sonnet" },
      },
    ],
  },
  {
    id: "tr-1e8820f4",
    query: "If Redis node 3 crashes, what is the fallback latency impact on our semantic cache?",
    timestamp: "2026-04-12 15:42:19",
    totalDurationMs: 12,
    totalTokens: 180,
    costUsd: 0.0001,
    route: "vector_search",
    cacheStatus: "hit",
    status: "success",
    spans: [
      {
        id: "sp-401",
        name: "cache.check",
        lane: "cache.redis",
        startMs: 0,
        durationMs: 12,
        status: "hit",
        attributes: { "cache.hit": true, "cache.cosine_sim": 0.965 },
      },
    ],
  },
];
