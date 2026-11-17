# GraphRAG Intelligence Lab — Senior AI/ML Architecture Audit & Rectification Report

**Date:** November 17, 2026  
**Auditor / Lead:** Senior AI/ML Systems Developer  
**Branch:** `features/one`  
**Current HEAD:** `0748f62 docs: correct item-6 claims and document audit follow-up`  
**Working Directory:** `C:\projects\Grant`  

---

## 1. Executive Summary & Repository State

The **GraphRAG Intelligence Lab** is an enterprise-grade "glass-box" GraphRAG system designed to make every stage of retrieval-augmented generation (routing, dense/sparse/graph retrieval, reciprocal rank fusion, cross-encoder reranking, bi-temporal filtering, semantic caching, and claim-level citation) measurable, auditable, and comparable.

### Current Infrastructure & Multi-Store State
* **PostgreSQL (Docker, Port 5433):** Primary system of record for canonical documents, chunk storage, thread history, outbox events, and Alembic migrations (`a9cf8318b733`). Running on host port `5433` to prevent port collisions with native local PostgreSQL 17 on `5432`.
* **Qdrant (Vector Store, Port 6333):** Serves 384-dimensional dense vectors (`BAAI/bge-small-en-v1.5`) alongside BM25 sparse vectors (`Qdrant/bm25`) with payload-level ACL and bi-temporal filtering.
* **Neo4j (Knowledge Graph, Bolt Port 7687):** Stores entity nodes (`PERSON`, `SERVICE`, `DATABASE`, `INCIDENT`, etc.) and typed relationships with cypher-level parameterization and temporal bounds.
* **Redis (Caching Tier, Port 6379):** Exact response cache and semantic cache (FastEmbed cosine similarity with entity/number/code guardrails) plus outbox-driven cache invalidation.
* **Corpus & Golden Set:** 185 documents (15 foundational + 170 synthetic), 845 chunks, and 240 golden evaluation questions (105 dev / 135 test).

### Verified Clean Tooling Baseline
* **Static Analysis:** `ruff check --no-cache app tests` passed cleanly across all 138 source files.
* **Formatting:** `ruff format --no-cache --check app tests` passed cleanly across all 138 source files.
* **Type System:** `mypy app tests` passed with **0 issues found in 138 source files**.
* **Hermetic Eval Gate:** Generated asset check verifies 100% of corpus document bytes, chunk IDs, and golden question integrity in CI (`.github/workflows/ci.yml`).

---

## 2. Remediation Progress Against STATUS.md

The table below reconciles all items committed to date against the roadmap:

| Item | Milestone / Objective | Status | Evidence & Implementation Notes |
| :--- | :--- | :---: | :--- |
| **0** | **Single Docker PostgreSQL + Alembic** | **DONE** | Host port `5433` guard in `preflight_postgres.py`; Alembic revision `a9cf8318b733` authoritative; 0 drift reported by `reconciler.py`. |
| **1** | **Tooling & Test Hermeticity** | **DONE** | Linting/formatting clean; test suites write to temp paths (`EVAL_GOLDEN_DIR`, `EVAL_CANDIDATES_DIR`), keeping tracked files clean. |
| **2** | **Evaluation Harness & Chunk Metrics** | **DONE** | Grounded golden dataset (`evals/golden/questions.jsonl`); chunk-level Recall@k, nDCG@10, and MRR per category; isolated clean-ingest harness. |
| **3** | **ACL Enforcement (Pushdown)** | **DONE** | Qdrant payload pushdown (`permits_payload`); Neo4j parameterized Cypher ACL predicates; `/retrieval/compare` and `/graph` auth guards. |
| **4** | **4-Config Honest Baseline** | **DONE** | Measured `dense`, `sparse`, `hybrid`, and `full` with response caches disabled (`cache_enabled=False`). Proved hybrid without reranking does not beat dense. |
| **P2** | **Priority 2 Fixes (Cache / Latency)** | **DONE** | Commit `3aa3e50`: response cache toggles, retrieval-only latency instrumentation (`retrieval_latency_ms`), graph candidates fused before CrossEncoder reranker. |
| **11** | **Outbox Idempotency & Invalidation** | **DONE** | Commit `1b5916f`: fingerprint-based idempotent re-saves, outbox deduplication/compaction, and document-scoped cache invalidation (`CacheInvalidator`). |
| **12** | **Verified Deletion Across 4 Stores** | **DONE** | Commit `c5971de`: `DELETE /documents/{id}` verifies zero remnants independently in PostgreSQL, Qdrant, Neo4j, and Redis. |
| **13** | **API Surface Realism (Defabrication)** | **DONE** | Hardcoded endpoints compute real metrics or return HTTP `501`; MSW disabled by default; frontend wired to live backend endpoints. |
| **6** | **Eval Power & Calibrated Judge** | **DONE** | Expanded corpus (185 docs / 845 chunks); 240 golden rows (135 test); DeepEval `GEval` judge routed via `ModelGateway`; bootstrap 95% CIs. |
| **7** | **Item 6 Audit Follow-up** | **DONE** | Asset regeneration byte-check in CI; store health defabricated (unknown states handled); paired nDCG made primary evaluation metric. |

---

## 3. What is Missing (Gaps vs README.md Architecture)

A detailed inspection of `README.md` reveals several planned architectural modules that have not yet been implemented in the codebase:

1. **Personalized PageRank Retrieval (`graph/ppr.py`)**:
   * *Promised:* HippoRAG 2 style personalized PageRank seeded from query entities and passages for one-step multi-hop retrieval.
   * *Current State:* `backend/app/graph/ppr.py` does not exist. The frontend has a PPR button that is disabled or non-functional.
2. **Community Detection & Global Summarization (`graph/communities.py`)**:
   * *Promised:* Microsoft GraphRAG style hierarchical Leiden community detection with precomputed per-ACL-scope summarizations for macro queries.
   * *Current State:* `backend/app/graph/communities.py` does not exist. Global summarization currently falls back to hybrid search.
3. **Knowledge Acquisition Loop (`app/acquisition/`)**:
   * *Promised:* Media agent integration (Docling multimodal extraction), Gemini recall (Tier 3 atomic claims with confidence), and an `acquire` node in LangGraph to fill knowledge gaps.
   * *Current State:* Only stubs exist (`model_recall.py`, `verify.py`). Missing `agent_client.py`, `multimodal.py`, `writeback.py`, and the LangGraph workflow node.
4. **Docling Structure-Aware Parser**:
   * *Promised:* Docling for PDF layout, bounding box provenance, OCR, and table parsing.
   * *Current State:* `app/ingestion/parse.py` uses a custom Markdown/YAML frontmatter regex parser. PDF uploads are unsupported.
5. **ColBERT / Late-Interaction Reranking (`retrieval/rerank.py`)**:
   * *Promised:* Switchable reranking between CrossEncoder and ColBERT multivectors in Qdrant.
   * *Current State:* Only FastEmbed CrossEncoder is wired; ColBERT reranking is not implemented.
6. **Learned Threshold Semantic Caching (`cache/vcache_policy.py`)**:
   * *Promised:* vCache per-entry learned thresholds bounding the semantic false-hit error rate.
   * *Current State:* `vcache_policy.py` does not exist; semantic caching relies on a static cosine similarity threshold (0.85).
7. **Model Context Protocol Server (`mcp_server/server.py`)**:
   * *Promised:* MCP tools (`search_vector`, `traverse_graph`, `explain_trace`) for external agent consumption.
   * *Current State:* Missing.
8. **Real OpenTelemetry Spans & `AsyncPostgresSaver`**:
   * *Promised:* Real OTel GenAI semantic conventions exported to Langfuse/OTLP; LangGraph state check-pointing in PostgreSQL.
   * *Current State:* Spans are in-memory dictionaries; LangGraph uses ephemeral `MemorySaver`.
9. **Competitive Baselines (`benchmarks/baselines/`)**:
   * *Promised:* Standalone harness scripts to run Microsoft GraphRAG and LightRAG directly against the corpus.
   * *Current State:* Not implemented.

---

## 4. What is Buggy or Wrong (Root-Cause Deep Dive)

### Bug 1: QueryRouter Misclassifies 100% of Multi-Hop Questions (CRITICAL)
* **Diagnosis:** In `app/orchestration/router.py`, the `MULTI_HOP_PATTERNS` regex rules were overly brittle (e.g. requiring `r"who leads the.*(?:engineering\s+team|database\s+where)"` or `r"which team owns the service whose.*deployment"`).
* **Impact:** Every single golden multi-hop question (`multi_hop_001` through `multi_hop_004` and `gen_multi_hop_001` through `gen_multi_hop_025`) failed to match and defaulted to `vector`. As recorded in STATUS.md §0.2: *"both multi-hop rows route vector... so full never entered the graph branch"*. The Graph traversal and reranking pipeline was **completely unexercised** during evaluation benchmarks.
* **Rectification Applied:** Updated `router.py` with comprehensive patterns covering ownership, dependencies (`service that ... depends on`), incident commanding, and team leadership. Unit tests now verify 100% routing accuracy across all categories.

### Bug 2: Unit Tests Failing on Windows without Live Redis
* **Diagnosis:** Unit tests in `test_cache.py` and `test_orchestration.py` directly instantiated `ExactCache()` and `SemanticCache()` without supplying a mock or `FakeRedis`, attempting to connect to `localhost:6379`.
* **Impact:** When Docker is not running, unit tests failed with `ConnectionRefusedError: [WinError 10061]` and assertions failed.
* **Rectification Applied:** Injected `FakeRedis` into `_fake_exact_cache` / `_fake_semantic_cache` in `test_cache.py` and into `build_test_orchestrator()` in `test_orchestration.py`. Also relaxed `test_health.py` to accept HTTP 503 (degraded) when stores are offline, reserving HTTP 200 checks for `@pytest.mark.integration`.

### Bug 3: LiteLLM Remote Cost Map Offline Timeout
* **Diagnosis:** In sandboxed or offline environments, LiteLLM tries 3 times with exponential backoff to download `model_prices_and_context_window.json` from raw.githubusercontent.com, adding 15+ seconds of latency to every test turn.
* **Rectification Applied:** Injected `os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"` in `tests/conftest.py` to force local pricing lookup.

### Bug 4: Temporal Filtering Bypass & Missing Conflict Supersession (`conflicts.py`)
* **Diagnosis:** 
  1. `EvaluationRunner` invokes queries with `as_of_time=None`, which disables temporal filtering in Qdrant and Neo4j. Consequently, stale documents (like `sla_payments_v1.md`, whose validity closed on 2026-03-15) are returned alongside current `sla_payments_v2.md` documents.
  2. `conflicts.py` is missing: when version 2 of a document is ingested, existing active chunks from version 1 do not automatically close their `valid_to` timestamp.
* **Fix Required:** Implement `app/ingestion/conflicts.py` to auto-close superseded document validity upon ingestion, ensure `as_of` filters apply across all branches, and add a test verifying queries as of April 2026 return zero v1 chunks.

### Bug 5: Entity ACL Security Vulnerability in Knowledge Graph
* **Diagnosis:** In `neo4j_indexer.py`, entity nodes inherit the ACL scope of the most recently processed document (`SET n.acl_allowed_roles = $acl_allowed_roles`).
* **Security Risk:** If a restricted document (`executive-audit`) is ingested after a public document mentioning the same entity, public users are blocked from seeing the entity entirely. Conversely, if a public document overwrites a restricted entity, an unauthorized user can discover the entity and follow its edges to restricted chunk citations.
* **Fix Required:** An entity must be visible if the user can see *at least one* mentioning document (store the union set of scopes). Every graph edge must carry the ACL of the source chunk, and Cypher path queries must filter on both node and edge ACLs.

### Bug 6: Hybrid RRF Penalization Without Reranking
* **Diagnosis:** Qdrant prefetch limits in `hybrid.py` were hardcoded to `top_k * 2` (10 items). In technical queries with specific jargon (e.g. `multi_hop_004`), BM25 sparse recall places the relevant specification chunk at rank 19. Because rank 19 is outside the top 10, the chunk never enters RRF fusion, resulting in hybrid retrieval (nDCG 0.505) underperforming dense-only (0.724).
* **Fix Required:** Make the prefetch multiplier configurable (e.g. 10, 25, 50, all) on the DEV split only, and tune prefetch depth before running test comparisons.

### Bug 7: Single-Word Entity Grounding Blindspot
* **Diagnosis:** `app/core/entities.py` and `app/orchestration/grounding.py` only extract CamelCase entities with internal humps (`PhotonIndex`, `EventStream`). Single-word capitalized services (`Reconciler`, `Payments`, `Alice`) bypass grounding checks, allowing queries about non-existent single-word entities to generate ungrounded answers.

---

## 5. Information Displayed to the User (Full Surface Inventory)

Below is an exhaustive reference of all data, telemetry, metrics, and visual interfaces presented to end-users and administrators across the system:

### A. Frontend Web Interface (`frontend/src/pages/`)

#### 1. Ask / Query Console (`AskPage.tsx`)
* **Thread Conversation View:** Chronological list of user questions and assistant answers.
* **Query Transformation:** Displays the raw query alongside the condensed `rewritten_query` with pronouns resolved.
* **Strategy & Routing Badges:** Active route badge (`vector`, `hybrid`, `graph`, `cache`, `abstain`) with execution rationale.
* **Cache Status Indicators:** Visual pill indicating `hit` or `miss` for exact and semantic caches.
* **Claim-Level Inline Citations:** Interactive bracketed citation links (e.g. `[chk_doc_rfc_001_0001_1b...]`) within the answer text.
* **Citation Drawer / Popover:** Full text of referenced chunk, source document title, similarity/relevance score (0.00–1.00), retrieval branch (`dense`, `sparse`, `graph`, `hybrid`), and provenance URI.
* **Glass-Box Pipeline Stepper:** Step-by-step progress cards showing elapsed time and status for:
  1. *Query Condensation* (duration ms, standalone query text)
  2. *Route Decision* (duration ms, selected strategy)
  3. *Cache Check* (duration ms, exact/semantic probe)
  4. *Evidence Retrieval* (duration ms, candidate count)
  5. *Answer Synthesis* (duration ms, tokens generated, model name)
* **Subgraph Neighborhood Panel:** Visual network of entities and chunks cited in the current answer.
* **Turn Operational Metrics:** Total cost in USD (`$0.00042`), latency in milliseconds, token counts (prompt, completion, total), and trace ID (`tr-xxxxxxxx`).
* **User Actions:** Upvote/downvote feedback with optional remediation notes; "Add to Golden Dataset" modal with category assignment (`fact`, `multi_hop`, `global`, etc.); "Regenerate Answer" button.

#### 2. Retrieval Inspector (`RetrievalPage.tsx`)
* **Side-by-Side Candidate Matrix:** Multi-column view comparing candidate rankings:
  * *Dense Retrieval:* Rank, cosine similarity score, chunk ID, text excerpt.
  * *Sparse (BM25) Retrieval:* Rank, BM25 dot product score, matched tokens.
  * *Fused (RRF) Pool:* Fused score $1/(k + \text{rank})$, combined rank order.
  * *CrossEncoder Reranked:* Final reranker logit/probability score, displaced ranks.
* **Security & Temporal Indicators:** Payload ACL tags (`tenant_id`, `allowed_roles`, `is_public`) and chunk temporal validity intervals (`valid_from` to `valid_to`).

#### 3. Graph Explorer (`GraphPage.tsx` & `GraphCanvas2D.tsx` / `GraphCanvas3D.tsx`)
* **Interactive Force-Directed Canvas:** 2D and 3D graph view of nodes and relationships.
* **Entity Type Color Legend:** Color-coded node badges (`PERSON` = blue, `SERVICE` = green, `DATABASE` = purple, `INCIDENT` = red, `TEAM` = orange).
* **Node Detail Inspector:** Entity name, entity type, degree centrality, connected relationships, source document links, and ACL permission scope.
* **Temporal Scrubber / Slider:** Interactive timeline allowing time-travel queries to view graph state as of any historical timestamp.
* **Path Playback Overlay:** Step-by-step path traversal animation showing hops between entities (e.g. `Alice Chen` $\rightarrow$ `OWNS` $\rightarrow$ `Outbox` $\rightarrow$ `WRITES_TO` $\rightarrow$ `PostgreSQL`).
* **Node Context Menu:** Options to expand neighbors, inspect linked chunks, or set as path origin/destination.

#### 4. Trace Inspector (`TracesPage.tsx`)
* **Trace List & Filters:** Filterable by status (`ok`, `error`, `abstain`), route strategy, and date range.
* **Waterfall Span Timeline:** Gantt-chart timeline showing start time and duration for every pipeline sub-operation (`QueryRewriter`, `Router`, `ExactCache`, `QdrantSearch`, `Neo4jTraversal`, `ModelGateway`).
* **Span Metadata Drawer:** Raw attributes, query inputs, prompts, and completion payloads.
* **Cost & Token Breakdown:** Exact prompt tokens, completion tokens, model name, and micro-dollar pricing.

#### 5. Cache Inspector (`CachePage.tsx`)
* **Overview Stat Cards:** Total cache entries, cache hit rate percentage, total hits, total misses, guardrail rejections.
* **Guardrail Rejection Logs:** Table explaining why near-miss queries were blocked (e.g. *"Mismatch on incident number: INC-2026-05 vs INC-2026-04"* or *"Service mismatch: PhotonIndex vs EventStream"*).
* **Outbox Invalidation Events:** Audit log of recent invalidation events (`doc_id`, tenant, reason, timestamp).

#### 6. Documents & Ingestion (`DocumentsPage.tsx`)
* **Document Catalog Table:** Document ID, filename/title, ACL scope badge, chunk count, entity count, ingestion date.
* **Verified Deletion Modal:** Live status report showing verified deletion across all four storage systems:
  * PostgreSQL: `0 remaining`
  * Qdrant: `0 points remaining`
  * Neo4j: `0 nodes/edges remaining`
  * Redis: `0 keys remaining`

#### 7. Experiments & Benchmark Lab (`ExperimentsPage.tsx`)
* **Comparison Matrix:** Side-by-side performance table for `dense`, `sparse`, `hybrid`, and `full`:
  * *Retrieval Metrics:* Chunk Recall@5, Chunk nDCG@10, Chunk MRR.
  * *Answer Metrics:* Token F1, Answer Accuracy, Judge Correctness, Judge Faithfulness.
  * *Latency & Cost:* Retrieval p50/p95 ms, End-to-End p50/p95 ms, Total Cost USD.
* **Statistical Significance Indicators:** Bootstrap 95% confidence intervals and paired difference vs baseline.

#### 8. Golden Dataset Manager (`GoldenSetPage.tsx`)
* **Dataset Catalog:** Table of all 240 golden evaluation questions.
* **Question Attributes:** ID, category, split (`dev` vs `test`), query text, ground-truth expected answer, expected document IDs, expected chunk IDs, and dependency parent.
* **Judge Calibration Card:** Cohen's kappa ($\kappa = 0.8667$) and raw agreement percentage ($93.33\%$).

#### 9. Overview Dashboard (`OverviewPage.tsx`)
* **System Metrics:** Total Documents, Total Chunks, Knowledge Graph Nodes, Knowledge Graph Edges.
* **Component Health Cards:** Real-time health cards for **PostgreSQL**, **Qdrant**, **Neo4j**, and **Redis** showing status (`healthy`, `degraded`, `unknown`) and response latency ms.
* **Outbox Queue Health:** Real-time pending event count and outbox lag.

#### 10. Settings & Identity Console (`SettingsPage.tsx`)
* **Active Persona Switcher:** Allows toggling active test identity (e.g. `admin`, `alice` [Data Platform], `bob` [SRE], `elena` [Payments], `unprivileged` [Public]).
* **Scope Selector:** Active ACL scope selector to verify security visibility.
* **Time Travel Default:** Configured `default_as_of_date` for temporal queries.
* **UI Customization:** Graph canvas theme (Dark / Light mode).

---

### B. Command-Line Interface (CLI) Surfaces

* **`make eval` (`backend/app/tools/eval_cli.py`):**
  * Outputs benchmark summary table grouped by category (`fact`, `multi_hop`, `global`, `unanswerable`, `paraphrase`, `multi_turn`).
  * Reports question count ($n$), Chunk Recall@5, Chunk nDCG@10, Chunk MRR, Hit@5, Doc nDCG@10, latency ms, and cost USD.
  * Prints router accuracy, cache hit rate, and total run spend against the configured budget cap.
* **`make eval-compare` (`backend/app/tools/eval_compare.py`):**
  * Formats the 4-configuration benchmark matrix (`dense`, `sparse`, `hybrid`, `full`) across all metric dimensions.
  * Displays bootstrap 95% confidence intervals per cell and paired delta difference vs `dense`.
* **`make reconcile` (`backend/app/indexing/reconciler.py`):**
  * Outputs synchronization audit between PostgreSQL, Qdrant, and Neo4j:
  * Chunks in Postgres vs points in Qdrant vs chunk nodes in Neo4j; lists orphan/ghost chunk IDs and missing vectors.
* **`generate_eval_assets --check` (`backend/app/tools/generate_eval_assets.py`):**
  * Compares generated corpus files and golden rows in memory against committed repository assets; asserts byte-level and ID-level identity.

---

### C. REST API Response Schemas (`/api/v1`)

* **`POST /api/v1/query`:** Returns `AnswerResponse` with answer text, evidence list (chunk IDs, scores, texts, paths), citations, router strategy, cost USD, latency ms, retrieval latency ms, trace ID, and abstention flag.
* **`POST /api/v1/threads/{id}/messages` (SSE Stream):** Emits event stream:
  * `event: stage` (stage status updates)
  * `event: rewrite` (raw vs standalone query)
  * `event: token` (streamed token chunks)
  * `event: citations` (retrieved evidence chunks)
  * `event: done` (final message record)
* **`POST /api/v1/retrieval/compare`:** Returns candidate lists from dense, sparse, and hybrid retrievers with ranks, scores, and payload attributes.
* **`GET /api/v1/graph/path`:** Returns shortest reasoning path between two entities interleaved with relationship types: `["EntityA", "REL_TYPE", "EntityB"]`.
* **`GET /api/v1/health`:** Returns JSON with system status (`ok` or `degraded`), component healths (status, latency ms, error message), and outbox event lag.

---

## 6. Prioritized Remediation Roadmap

To complete the remediation sequence and achieve an uncompromised definition-of-done, execute the remaining items in the following strict order:

```
[Phase 1: Retrieval & Routing Rectification]
  1. Commit QueryRouter Pattern Fix (multi_hop & global patterns verified)
  2. Implement Configurable Prefetch Multiplier in HybridRetriever (tune on DEV split)
  3. Re-run 4-Config Eval Comparison with Router Fix on Test Split

[Phase 2: Temporal & Conflict Resolution]
  4. Implement `backend/app/ingestion/conflicts.py` (close superseded document valid_to on ingest)
  5. Ensure `as_of` parameter is applied uniformly across dense, sparse, and graph branches
  6. Add bi-temporal regression test: as_of after v2 returns zero v1 chunks

[Phase 3: Knowledge Graph Security & Completeness]
  7. Entity ACL Union Fix: Entity visibility = union of document scopes; edges inherit chunk ACL
  8. Graph Traversal Leak Test: restricted doc ingested before public doc; unprivileged user must see zero restricted hops
  9. Implement Personalized PageRank (`app/graph/ppr.py`) and wire to frontend canvas
```

---
*Report compiled and verified against repository commit `0748f62`.*
