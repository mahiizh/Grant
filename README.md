# GraphRAG Intelligence Lab — Design Review

·

## What you're building

You're building a glass-box RAG system: a working GraphRAG engine whose every decision (route, retrieve, fuse, cache, generate) is visible, measurable and comparable. It has three jobs at once:

- **An engine** that answers questions using vector, lexical and graph retrieval, fused and reranked.
- **A teaching lab** that shows graph traversal, vector neighbours, cache decisions and request traces in a UI.
- **A benchmark harness** that compares configurations on quality, latency and cost with reproducible runs.

The README is unusually mature for a planned project: it already bounds graph depth and retries, separates estimated model cost from infra cost, treats similarity as a ranking signal rather than a probability, and puts authorization on the cache path. The flaws below are mostly about **scope, sequencing and a few missing primitives**, not wrong ideas.

## Overall verdict

The concepts are right; the plan is too wide and in the wrong order. The three changes that matter most:

1. **Build the evaluation harness first, not last.** Without a baseline you can't tell whether graph retrieval, reranking or caching helped. The ICLR 2026 GraphRAG-Bench paper found GraphRAG often loses to plain vector RAG on simple fact questions, so "does the graph help here?" must be measured from day one.
2. **Cut the infrastructure in half for v1.** The README needs Neo4j, Qdrant, Redis, PostgreSQL, an OTel collector and Langfuse. Self-hosted Langfuse alone is six services (web, worker, Postgres, ClickHouse, Redis, object storage). That's 10+ containers before you write retrieval code.
3. **Add the missing primitives:** time (facts change), entity resolution as a first-class stage, a data model shared across stores, and a model gateway for cost tracking.

Everything else is refinement.

## Design flaws and fixes

Fourteen issues, highest impact first. The first six would block a "top-end" result; the rest are polish.

| # | Severity | Flaw in the README | Why it hurts | Fix |
| --- | --- | --- | --- | --- |
| 1 | High | Evaluation arrives in Phase 9 | Phases 2–8 are built blind; you can't prove graph, rerank or cache helped | Build a 50–100 question golden set (fact, multi-hop, global, unanswerable, paraphrase) before any retrieval code. Gate every PR on it with DeepEval in CI |
| 2 | High | 10+ services for local dev | Neo4j + Qdrant + Redis + Postgres + OTel collector + self-hosted Langfuse (6 services). Setup eats the learning time | v1: Qdrant, Neo4j, Postgres, Redis only. Use Langfuse Cloud free tier or Arize Phoenix locally. Swap in self-hosted Langfuse once everything else runs |
| 3 | High | No time model; "conflicting facts" and "document updates" have no mechanism | Old facts and new facts sit side by side; the graph can't answer "what was true in March?" | Bi-temporal edges: `valid_from`, `valid_to`, `ingested_at`, `source_version`. Invalidate contradicted edges, never delete (Graphiti's pattern) |
| 4 | High | Three stores hold copies of the same chunks with no consistency plan | A deleted document lingers in Qdrant or Neo4j; cache serves it; citations break | Postgres is the source of truth for `doc_id`, `chunk_id`, `version`, ACL. Writes go through an outbox table; idempotent indexers sync Qdrant and Neo4j; a nightly reconciler diffs them |
| 5 | High | Graph permissions are "applied" but not designed | A traversal can reach allowed nodes through a forbidden edge; community summaries blend restricted text | ACL labels on every chunk, node, edge and summary. Filter inside the Cypher `MATCH`, not after. Build summaries per permission scope. Add leak tests to the eval set |
| 6 | High | Indexing cost is ignored; only per-request cost is tracked | LLM entity extraction over a corpus is usually the biggest bill in GraphRAG | Track cost per document indexed. Cache extraction calls by content hash. Benchmark a lazy/incremental mode (LazyGraphRAG, LightRAG) against full extraction |
| 7 | Med | Semantic cache stores final answers behind one global threshold | A RAG answer depends on the index version and the user's permissions, not just the query. A global threshold trades hit rate against wrong hits | Key exact cache on (normalized query, ACL scope, index version, prompt version). Guard semantic hits on entities, numbers and dates. Try per-entry learned thresholds (vCache) as an experiment |
| 8 | Med | Entity resolution is one bullet in Phase 3 | Duplicate entities silently break multi-hop paths; it's the hardest quality problem in graph construction | Make it its own stage: blocking → embedding match → LLM adjudication. Measure merge precision and recall on a labelled sample |
| 9 | Med | Lexical retrieval is a separate box with no engine named | Another service, plus score fusion across systems | Store BM25 as Qdrant sparse vectors and fuse with RRF in one Query API call |
| 10 | Med | Cost math and pricing versions are hand-rolled | Model prices change often; you'd maintain your own price table | Route all model calls through LiteLLM: maintained cost map, per-key and per-tag budgets. Microsoft GraphRAG already depends on it |
| 11 | Med | OTel and Langfuse instrumented separately | Two schemas, duplicate spans | Instrument once with OTel GenAI semantic conventions and export to Langfuse over OTLP. Pin the convention version: it's still in Development status |
| 12 | Med | LLM query router with no measure of its own accuracy | A wrong route costs latency and quality invisibly | Start with rules plus a small classifier. Label the best strategy per eval question and report router accuracy and regret |
| 13 | Low | "Parse" is unspecified; citations are "where possible" | Tables and PDFs are where RAG quality dies; weak citations hide hallucinations | Use Docling with structure-aware chunking; keep page and bounding-box provenance. Require claim-level citations and abstain when evidence is thin |
| 14 | Low | Five separate UIs planned | Front-end work swamps the back end | Build one trace-centric request inspector first; graph explorer and experiment lab hang off it |

## GitHub projects to study or reuse

Use libraries for plumbing and reimplement the ideas you want to learn. "Reuse" means take it as a dependency; "Study" means read the code, then build your own version and benchmark it against theirs.

| Project | Use | What to take from it | Your module |
| --- | --- | --- | --- |
| [microsoft/graphrag](https://github.com/microsoft/graphrag) | Study + baseline | Community detection and summaries, local vs global search, incremental `update`. Run it as the reference GraphRAG in your benchmark (v3.1.x in 2026) | `graph/`, `evaluation/` |
| [HKUDS/LightRAG](https://github.com/HKUDS/LightRAG) | Study + baseline | Dual-level (entity / theme) retrieval, incremental graph updates without rebuilds; \~39k stars, EMNLP 2025 paper | `retrieval/`, `ingestion/` |
| [OSU-NLP-Group/HippoRAG](https://github.com/OSU-NLP-Group/HippoRAG) | Study | Personalized PageRank seeded from query entities and passages: multi-hop in one retrieval step. Best algorithm to implement yourself | `graph/` |
| [getzep/graphiti](https://github.com/getzep/graphiti) | Study | Bi-temporal edges with `invalid_at`, episode provenance, hybrid semantic + keyword + graph search, MCP server | `graph/`, `ingestion/` |
| [neo4j/neo4j-graphrag-python](https://github.com/neo4j/neo4j-graphrag-python) | Reuse | `VectorCypherRetriever`, `HybridCypherRetriever`, `Text2CypherRetriever`, `SimpleKGPipeline`. Saves weeks of Cypher glue | `graph/`, `retrieval/` |
| [docling-project/docling](https://github.com/docling-project/docling) | Reuse | Layout, reading order, tables, OCR into one lossless document model; MIT, runs locally | `ingestion/` |
| [qdrant/fastembed](https://github.com/qdrant/fastembed) | Reuse | BM25 / SPLADE sparse vectors and ColBERT multivectors for Qdrant hybrid search and reranking | `retrieval/` |
| [redis/redis-vl-python](https://github.com/redis/redis-vl-python) | Reuse | `SemanticCache` with TTL, adjustable distance threshold and filterable fields for per-user scoping | `cache/` |
| [vcache-project/vCache](https://github.com/vcache-project/vCache) | Study | Per-entry learned thresholds with a user-set error bound (ICLR 2026). Great experiment against a static threshold | `cache/` |
| [BerriAI/litellm](https://github.com/BerriAI/litellm) | Reuse | One API for all providers, maintained model cost map, provider / model / tag budgets | `llm/`, `observability/` |
| [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) | Reuse | Stable since 1.0 (Oct 2025): checkpointers, interrupts, durable resume | `orchestration/` |
| [langfuse/langfuse](https://github.com/langfuse/langfuse) | Reuse | OTel-native traces, token cost, evals, prompt versions; MIT core | `observability/` |
| [GraphRAG-Bench/GraphRAG-Benchmark](https://github.com/GraphRAG-Bench/GraphRAG-Benchmark) | Reuse | Tiered tasks (fact → reasoning → summarization) for testing when graphs help | `evaluation/` |
| [explodinggradients/ragas](https://github.com/explodinggradients/ragas) + [confident-ai/deepeval](https://github.com/confident-ai/deepeval) | Reuse | Ragas for faithfulness and context metrics; DeepEval for pytest-style CI gates | `evaluation/` |
| [FalkorDB/FalkorDB](https://github.com/FalkorDB/FalkorDB) | Optional | Redis-protocol graph DB aimed at GraphRAG; a second graph backend to benchmark against Neo4j | `graph/` |

Avoid Kuzu: it was archived in October 2025 and is read-only.

## Concepts to add

Turn each concept into an experiment with a measured result; that's what makes this a top-end project rather than a tutorial clone.

| Concept | Why it's current | Experiment to run in your lab |
| --- | --- | --- |
| When graphs help vs hurt | GraphRAG-Bench (ICLR 2026) shows vanilla RAG matches or beats GraphRAG on simple fact retrieval | Vector-only vs graph vs hybrid, scored per question category. Publish the crossover chart |
| Personalized PageRank retrieval | HippoRAG 2 does multi-hop in one step by seeding PPR with query entities and passages | Implement PPR yourself; compare with BFS k-hop and iterative retrieval on recall@k and latency |
| Bi-temporal knowledge graphs | Graphiti tracks when a fact was true and when it was learned, invalidating rather than deleting | Ingest two versions of a doc; ask "as of" questions; measure stale-answer rate with and without temporal filters |
| Lazy and incremental indexing | LazyGraphRAG claims indexing cost on par with vector RAG, about 0.1% of full GraphRAG | Full extraction vs lazy vs incremental: indexing dollars per 1k pages against answer quality |
| Sparse + dense hybrid with RRF | Qdrant's Query API fuses BM25 sparse and dense prefetches server-side | Dense vs BM25 vs RRF vs distribution-based fusion on queries with IDs, codes and acronyms |
| Late-interaction reranking | ColBERT multivectors sit between bi-encoders and cross-encoders on speed and accuracy | Cross-encoder vs ColBERT rerank: nDCG@10 gain per added millisecond |
| Error-bounded semantic caching | vCache learns a threshold per cached prompt and bounds the error rate | Static thresholds (0.05–0.3) vs vCache: hit rate against wrong-hit rate on a paraphrase / near-miss set |
| Provider prompt caching | Distinct from semantic caching: reuses the model's prompt prefix; OTel GenAI added cache-token attributes in v1.40 | Put the system prompt and stable context first; track cache-read tokens and cost saved per request |
| Durable agentic orchestration | LangGraph 1.0 checkpoints every node; runs survive restarts and can pause for review | Adaptive route with an evidence check and one bounded retry; report cost per *correct* answer, not per request |
| GenAI-standard telemetry | OTel GenAI conventions now cover inference, embeddings, retrieval, agents and MCP | Emit `gen_ai.*` spans for every stage; build p50/p95 per stage from `gen_ai.client.operation.duration` |
| MCP server for your retrievers | Graphiti and Docling both ship MCP servers; it's how agents consume retrieval now | Expose `search_vector`, `traverse_graph`, `explain_trace` as MCP tools; query your lab from Claude |
| Indirect prompt-injection defense | Retrieved text is untrusted input | Seed the corpus with poisoned docs; measure attack success rate before and after delimiting and instruction filtering |
| Judge calibration | LLM-as-judge scores drift and flatter | Hand-label a sample of answers (the committed artifact uses 30); report judge agreement (Cohen's kappa) and who authored the labels before trusting automated scores |

## Revised architecture

The stores stay the same; what changes is who owns the truth and how changes flow. A cache hit returns at the cache step; everything else runs the full path.

&#91;embedded content: revised architecture · query path and ingestion path\]

- **Removed:** the standalone lexical service (BM25 now lives in Qdrant) and the separate OTel + Langfuse instrumentation (one OTel pipeline exports to Langfuse).
- **Added:** an outbox in Postgres, an entity-resolution stage, LiteLLM as the only door to models, and temporal + ACL filters inside graph queries.
- **Optional extras:** self-hosted Langfuse (with ClickHouse), FalkorDB comparison, multi-tenant summaries.

## Knowledge acquisition: your agent + Gemini

Both sources fit, with one rule: nothing enters the graph without a source label and a trust level. When the graph can't answer, the system asks your media agent and Gemini, verifies what comes back, writes it in, and retrieves again. The next time the same question comes up, it's answered straight from the graph.

&#91;embedded content: knowledge acquisition loop\]

### Three source tiers

| Tier | Source | How it's stored | How it's used |
| --- | --- | --- | --- |
| 1 | Your ingested documents | Normal provenance: document, version, page | Can answer and be cited on its own |
| 2 | Your media agent | Full content plus source URI, media type, capture time; goes through the normal ingestion pipeline | Can answer and be cited; down-weighted when the source is old or unclear |
| 3 | Gemini recall: the model answering from its own training knowledge, the way I've answered in this conversation | Atomic claims with model name, prompt version, date and the model's confidence; flagged `unverified` | Never the only support for an answer; shown as "model knowledge"; promoted to tier 2 once a document or your agent confirms it |

Tier 3 is kept separate for a specific reason: model recall can be confidently wrong. If unverified recall is stored and later retrieved as evidence, the system starts citing itself and errors compound. The flag stops that loop.

### Connecting your agent

- Wrap it behind one fixed contract: `search(query, media_types, scope) → [{content, source_uri, media_type, captured_at, metadata}]`. If it already speaks MCP, connect to it as an MCP client; otherwise use a small HTTP adapter.
- Turn non-text results into text before extraction. Docling transcribes audio and reads images; Gemini is multimodal and can describe images and video frames. Keep the original file and link to it by source URI.
- Treat everything the agent returns as untrusted input and run it through the same prompt-injection filter as documents.

### Using Gemini

- Call it through LiteLLM with your `GEMINI_API_KEY`, so Gemini usage gets the same cost tracking and budgets as every other model call.
- Give it three jobs: generation and extraction, recall (tier 3), and describing media.
- Ask for recall as short, atomic facts with a confidence score, not prose, so each one maps cleanly to a graph edge.
- You can also use Gemini for embeddings, but pick one embedding model and stick with it: switching means re-embedding everything.

### Write-back rules

- **Store the raw episode first.** Every agent result and Gemini response is saved verbatim in Postgres with the query, time, and agent or model version. Graph facts link back to it, so you can always audit or rebuild.
- **Merge, don't duplicate.** Entity resolution matches new entities to existing ones. A fact confirmed by a second source adds that source to the existing edge and raises its trust.
- **Resolve conflicts by tier.** A new fact closes an old edge's validity only if it comes from an equal or higher tier; otherwise both are kept and flagged for review.
- **Bound it.** Cap agent calls and recall calls per request. Run write-back asynchronously so the user isn't waiting on ingestion.
- **Scope it.** Results inherit the asking user's permission scope, so something one user's agent found privately doesn't leak to others.

### Measuring it

- **Recall accuracy:** hand-check a sample of stored tier-3 facts against known answers.
- **Promotion rate:** the share of tier-3 facts later confirmed by tier 1 or 2.
- **Repeat-question savings:** latency and cost when a question is asked again and answered from the graph without calling the agent or Gemini.

### Repo additions

- `backend/app/acquisition/`: `agent_client.py` (adapter for your agent), `model_recall.py` (Gemini recall prompts), `multimodal.py` (media to text), `verify.py` (cross-checks and trust scoring), `writeback.py` (episode store into the ingestion pipeline)
- `domain/provenance.py`: tier, source URI, model, confidence, verification status
- A new `acquire` node in the LangGraph workflow between `check_evidence` and `generate`
- Settings: `GEMINI_API_KEY`, `EXTERNAL_AGENT_URL`, `ACQUISITION_ENABLED`, `MAX_ACQUISITION_CALLS`, `MIN_TRUST_TO_CITE`

## Final product structure

This is the complete product in one tree: every module from the design review has a home, so you can build it end to end in one stretch. Modules depend only downward (`api` → `orchestration` → `retrieval`/`graph`/`cache` → `domain`), so you can work on any folder without waiting on another.

```text
graphrag-intelligence-lab/
├── backend/
│   ├── pyproject.toml                 # uv-managed; Python 3.11+
│   ├── app/
│   │   ├── main.py                    # FastAPI app factory, lifespan, OTel bootstrap
│   │   ├── api/
│   │   │   ├── routes/
│   │   │   │   ├── query.py           # POST /query (streaming), GET /query/{id}
│   │   │   │   ├── ingest.py          # upload, re-ingest, delete document
│   │   │   │   ├── traces.py          # per-request trace, spans, cost breakdown
│   │   │   │   ├── graph.py           # neighborhood, path, PPR explorer endpoints
│   │   │   │   ├── cache.py           # inspect entries, explain hit/miss, invalidate
│   │   │   │   ├── experiments.py     # run/compare benchmark configs
│   │   │   │   └── health.py          # liveness, readiness, store checks
│   │   │   └── schemas/               # Pydantic request/response models
│   │   ├── core/
│   │   │   ├── config.py              # typed settings, validated at startup
│   │   │   ├── auth.py                # identity, tenant
│   │   │   ├── acl.py                 # ACL scope object passed to every store
│   │   │   ├── request_context.py     # request ID, deadline, cost budget
│   │   │   └── errors.py
│   │   ├── domain/
│   │   │   ├── models.py              # Document, Chunk, Entity, Relation, Evidence, Answer
│   │   │   ├── ids.py                 # stable doc_id / chunk_id / entity_id scheme
│   │   │   ├── temporal.py            # valid_from, valid_to, ingested_at, source_version
│   │   │   └── provenance.py          # tier, source URI, model, confidence, verified
│   │   ├── db/
│   │   │   ├── postgres.py            # session, repositories (source of truth)
│   │   │   ├── outbox.py              # index events written in the same transaction
│   │   │   └── migrations/            # Alembic
│   │   ├── ingestion/
│   │   │   ├── parse.py               # Docling → structured doc with page/bbox provenance
│   │   │   ├── chunking.py            # structure-aware chunks
│   │   │   ├── extraction.py          # typed entity/relation extraction (Pydantic schema)
│   │   │   ├── entity_resolution.py   # blocking → embedding match → LLM adjudication
│   │   │   ├── conflicts.py           # invalidate contradicted edges, never delete
│   │   │   └── pipeline.py            # end-to-end ingest + per-document indexing cost
│   │   ├── indexing/
│   │   │   ├── outbox_worker.py       # consumes outbox, idempotent upserts
│   │   │   ├── qdrant_indexer.py      # dense + BM25 sparse + optional ColBERT vectors
│   │   │   ├── neo4j_indexer.py       # nodes, edges, chunk links, ACL labels
│   │   │   └── reconciler.py          # nightly diff Postgres vs Qdrant vs Neo4j
│   │   ├── retrieval/
│   │   │   ├── dense.py
│   │   │   ├── sparse.py
│   │   │   ├── hybrid.py              # Qdrant prefetch + RRF / DBSF fusion
│   │   │   ├── rerank.py              # cross-encoder and ColBERT, switchable
│   │   │   └── filters.py             # ACL + temporal filters shared by all retrievers
│   │   ├── graph/
│   │   │   ├── schema.cypher          # constraints, indexes, vector index
│   │   │   ├── retrievers.py          # VectorCypher, HybridCypher, Text2Cypher (bounded)
│   │   │   ├── ppr.py                 # Personalized PageRank retrieval (HippoRAG-style)
│   │   │   ├── communities.py         # community detection + per-ACL-scope summaries
│   │   │   └── algorithms/            # hand-built for learning: bfs, dfs, dijkstra, astar, ppr
│   │   ├── orchestration/
│   │   │   ├── state.py               # LangGraph state
│   │   │   ├── router.py              # rules + small classifier; logs decision
│   │   │   ├── nodes/                 # retrieve, fuse, check_evidence, acquire, generate, abstain
│   │   │   ├── workflow.py            # graph wiring, one bounded retry, budgets
│   │   │   └── checkpointer.py        # Postgres checkpointer
│   │   ├── cache/
│   │   │   ├── keys.py                # query + ACL scope + index version + prompt version
│   │   │   ├── exact.py
│   │   │   ├── semantic.py            # RedisVL SemanticCache
│   │   │   ├── guards.py              # entity / number / date mismatch checks
│   │   │   ├── vcache_policy.py       # per-entry learned thresholds (experiment)
│   │   │   └── invalidation.py        # driven by outbox events
│   │   ├── acquisition/
│   │   │   ├── agent_client.py        # adapter for your media agent (MCP or HTTP)
│   │   │   ├── model_recall.py        # Gemini recall: atomic facts + confidence
│   │   │   ├── multimodal.py          # images, audio, video → text
│   │   │   ├── verify.py              # cross-checks, trust tier scoring
│   │   │   └── writeback.py           # raw episode → ingestion pipeline
│   │   ├── llm/
│   │   │   ├── gateway.py             # LiteLLM: all model + embedding calls
│   │   │   ├── prompts/               # versioned prompt files
│   │   │   └── citations.py           # claim-level citation check
│   │   ├── security/
│   │   │   ├── injection.py           # delimit + filter retrieved text
│   │   │   └── redaction.py           # log redaction rules
│   │   ├── observability/
│   │   │   ├── tracing.py             # OTel GenAI spans for every stage
│   │   │   ├── cost.py                # request + indexing cost, pricing version stored
│   │   │   └── metrics.py             # p50/p95/p99 per stage, cache hit/wrong-hit
│   │   ├── evaluation/
│   │   │   ├── datasets.py            # load versioned golden sets
│   │   │   ├── retrieval_metrics.py   # recall@k, precision@k, MRR, nDCG
│   │   │   ├── judges.py              # Ragas faithfulness, answer quality
│   │   │   ├── judge_calibration.py   # agreement with human labels
│   │   │   ├── router_regret.py       # chosen vs best strategy per question
│   │   │   └── runner.py              # run a config, store results
│   │   └── mcp_server/
│   │       └── server.py              # tools: search_vector, traverse_graph, explain_trace
│   └── tests/
│       ├── unit/
│       ├── integration/               # against real containers
│       ├── eval_gate/                 # DeepEval thresholds run in CI
│       └── security/                  # ACL leak cases, prompt-injection cases
├── frontend/
│   └── src/
│       ├── app/                       # routing, layout, auth
│       ├── lib/api.ts                 # typed client generated from OpenAPI
│       └── features/
│           ├── query-console/         # ask, stream answer, citations
│           ├── trace-inspector/       # span timeline, tokens, cost per stage
│           ├── retrieval-inspector/   # dense vs sparse vs fused vs reranked lists
│           ├── graph-explorer/        # paths, PPR scores, temporal slider
│           ├── cache-inspector/       # why it hit or missed
│           └── experiment-lab/        # side-by-side config comparison
├── evals/
│   ├── golden/                        # questions.jsonl with category, expected sources, paths
│   ├── adversarial/                   # poisoned docs, ACL leak probes
│   └── cache/                         # paraphrases and near-misses with labels
├── benchmarks/
│   ├── configs/                       # one YAML per retrieval/cache/router setup
│   ├── baselines/                     # MS GraphRAG, LightRAG runners on your corpus
│   └── results/                       # versioned outputs
├── corpus/                            # sample technical documents (licensed)
├── infra/
│   ├── docker-compose.yml             # api, workers, postgres, qdrant, neo4j, redis
│   ├── compose.observability.yml      # otel-collector (+ self-hosted Langfuse, optional)
│   ├── litellm.yaml                   # models, pricing overrides, budgets
│   └── otel-collector.yaml
├── .github/workflows/
│   ├── ci.yml                         # lint, typecheck, unit tests, asset check, hermetic eval gate
├── docs/
│   ├── architecture.md
│   ├── adr/                           # one file per design decision
│   └── experiments/                   # write-up per experiment with charts
├── Makefile                           # up, ingest, eval, bench, test
├── .env.example
└── README.md
```

### Stack per layer

| Layer | Tools |
| --- | --- |
| API | FastAPI, Pydantic, Uvicorn |
| Orchestration | LangGraph with Postgres checkpointer |
| Stores | PostgreSQL, Qdrant, Neo4j, Redis (RedisVL) |
| Ingestion | Docling, FastEmbed, neo4j-graphrag `SimpleKGPipeline` as a reference |
| Models | LiteLLM in front of every LLM, embedding and rerank call |
| Observability | OpenTelemetry GenAI conventions → Langfuse |
| Evaluation | Ragas, DeepEval, GraphRAG-Bench data |
| Frontend | React, TypeScript, a graph renderer such as Cytoscape.js or Sigma.js |

### Definition of done

The product is complete when all of these hold:

- [ ] `make up && make ingest && make eval` runs from a clean clone
- [ ] Every request has one trace with per-stage latency, tokens and cost
- [ ] Golden-set scores are reported per category; CI runs the generated-asset check and the
      hermetic eval gate (structure and safety invariants, not tuned quality thresholds)
- [ ] Hybrid retrieval beats dense-only on nDCG@10 (measured baseline: it does **not**; see
      `STATUS.md` §0.1–§0.2)
- [ ] Graph retrieval wins on multi-hop questions without losing on fact lookups
- [ ] Deleting a document removes it from Qdrant, Neo4j and the cache (reconciler clean)
- [ ] Zero results from ACL leak tests; prompt-injection success rate measured and reported
- [ ] Semantic cache wrong-hit rate is measured and under your chosen bound
- [ ] MS GraphRAG and LightRAG baselines are run on your corpus and compared
- [ ] Each experiment has a write-up in `docs/experiments/`

## Local setup

### Prerequisites

- Docker Desktop (or Docker Engine + Compose v2)
- [`uv`](https://docs.astral.sh/uv/) for the Python backend
- Node.js 20+ for the frontend

Copy `.env.example` to `.env` and set the secrets you need (`GEMINI_API_KEY` may also live in
`backend/.env`). Both files are git-ignored; only `.env.example` is tracked.

### One PostgreSQL, and it must be the Docker one

The whole stack (app, ingestion CLI, reconciler, Alembic) resolves `DATABASE_URL` from the same
settings, and Docker Compose publishes PostgreSQL on **host port 5433 by default**. That port was
chosen so the project's Docker Postgres can coexist with a native PostgreSQL installation that
already owns the default 5432: both servers can run at the same time without either one shadowing
the other. The host port is controlled by `POSTGRES_PORT`, which must agree in `.env`,
`infra/docker-compose.yml`, and the backend defaults.

A second PostgreSQL on the *same* port is still dangerous: one server can win IPv4 and another
IPv6, and part of the stack silently writes to the wrong database. To prevent that, `make up` runs
a preflight check and **fails** if the configured port is already served by anything that is not
the project's Docker Postgres.

If something else is listening on the configured port, stop it (or pick another free
`POSTGRES_PORT`). You do **not** need to stop a native PostgreSQL on 5432 — that is the point of
using 5433.

**Windows (elevated PowerShell), only if the service owns the configured port:**

```powershell
Get-Service *postgres*
Stop-Service <name>
```

**macOS:**

```bash
brew services stop postgresql@17
```

**Linux (systemd):**

```bash
sudo systemctl stop postgresql
```

### Bring-up

```bash
make up          # preflight + docker compose up -d --wait (Postgres, Qdrant, Neo4j, Redis)
make migrate     # Alembic upgrade head; creates/updates the schema
make ingest      # also runs migrate first
make reconcile   # also runs migrate first; verifies Postgres/Qdrant/Neo4j consistency
make dev         # also runs migrate first; starts the API on :8000
```

Alembic is the only way the production schema changes. The app, the ingestion CLI, and the
reconciler all verify that `alembic_version` exists at startup and refuse to run if it does not,
so a fresh clone must run `make migrate` (which the targets above do for you). Applying
`Base.metadata.create_all` is reserved for the test suite.

Each of those processes logs the resolved `DATABASE_URL` (password redacted) and the identity of
the server that answers it (`inet_server_port`, `data_directory`), so it is obvious whether a run
is talking to the Docker Postgres or to a stray native install. By default the URL is
`postgresql+asyncpg://…@localhost:5433/graphrag_lab`.

## Sources

- [When to use Graphs in RAG (GraphRAG-Bench), ICLR 2026](https://liner.com/review/when-to-use-graphs-in-rag-a-comprehensive-analysis-for)
- [GraphRAG-Bench repository](https://github.com/Powerkrieger/GraphRAG-Benchmark)
- [Microsoft GraphRAG 1.0 and LazyGraphRAG announcement](https://www.microsoft.com/en-us/research/blog/moving-to-graphrag-1-0-streamlining-ergonomics-for-developers-and-users/)
- [LazyGraphRAG cost figures](https://www.thestack.technology/microsoft-lazygraphrag/)
- [Microsoft GraphRAG v3.1.2 release](https://sourceforge.net/projects/graphrag.mirror/files/v3.1.2/)
- [LightRAG overview](https://www.beri.net/learning/lightrag-graph-rag-docs)
- [HippoRAG 2 paper](https://arxiv.org/html/2502.14802)
- [Graphiti README](https://github.com/peabodyAdmin/graphiti) and [Zep temporal KG paper summary](https://signals.aktagon.com/articles/2026/07/zep-a-temporal-knowledge-graph-architecture-for-agent-memory/)
- [neo4j-graphrag retrievers](https://docsearch.algolia.com/mcp/docs/repo/neo4j/neo4j-graphrag-python)
- [Docling](https://github.com/api-evangelist/docling)
- [Qdrant hybrid search](https://qdrant.tech/documentation/search-tuning/hybrid-search/) and [multivector reranking](https://qdrant.tech/documentation/tutorials-search-engineering/using-multivector-representations/)
- [RedisVL SemanticCache API](https://redis.io/docs/latest/develop/ai/redisvl/0.27.1/api/cache/)
- [vCache: Verified Semantic Prompt Caching](https://arxiv.org/html/2502.03771v5)
- [LiteLLM spend tracking](https://docs.litellm.ai/docs/proxy/cost_tracking.md) and [budget routing](https://docs.litellm.ai/docs/proxy/provider_budget_routing.md)
- [OpenTelemetry GenAI conventions status](https://www.truefoundry.com/blog/opentelemetry-genai-semantic-conventions) and [version timeline](https://www.greptime.com/blogs/2026-05-09-opentelemetry-genai-semantic-conventions)
- [Langfuse v3 self-host stack](https://railway.com/deploy/langfuse-llm-observability)
- [LangGraph 1.0 GA](https://changelog.langchain.com/announcements/ann_lxOZRCoFw2Qn9)
- [RAG evaluation tools compared](https://futureagi.com/blog/best-rag-evaluation-tools-2026/)
- [Kuzu archived; FalkorDB migration](https://www.falkordb.com/blog/kuzudb-to-falkordb-migration/)
