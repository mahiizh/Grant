# Grant revamp plan

## Goal
Upload a document → its entities appear in the graph. Ask anything → answer from docs,
else the web (graspreach), else model knowledge, labeled by source. Every question,
answer, document and web page is connected in one graph (the connected history).

## Rules for all work
- Isolated test stores only: `graphrag_lab_test`, `*_test` Qdrant collections, Neo4j 7688,
  Redis DB 1. Never touch dev stores.
- One commit per item. Full suite passes before each commit.
- After each item, run the live baseline harness and put the key numbers in the commit message.
- Targets: upload < 1 s, health during ingest < 100 ms, cache hit < 50 ms,
  docs Ask p95 < 4 s, web Ask p95 < 15 s, API < 1.5 GB, worker < 3 GB.
- If anything is ambiguous, stop and ask. Don't guess.
- Reread this file before each step.

## Done
- Step 0: cleanup (lab-only subsystems removed, owner/shared ACL, bi-temporal removed).
- Step 1: models built once and warmed, bounded executor, GLiNER off the Ask path,
  entity-seed search, LiteLLM num_retries=1 / timeout=30, 45 s Ask budget.
- Step 2: background ingestion worker; upload returns 202 + job; status endpoint; UI polling.
- Step 3: exact answer cache (commit 70d1a09).

## Decisions
- Reranker: ONNX int8, top 10 candidates, truncated to 256 tokens, one batched call.
  If the stage takes ≥ ~800 ms, `RERANK_ENABLED=false` by default (keep the code and setting).
  No time-boxed partial scoring: results must not depend on machine load.
- Evidence gate: dense cosine ≥ `EVIDENCE_MIN_DENSE_COSINE` (default 0.55), plus a NOT_FOUND
  marker from the grounded prompt. On NOT_FOUND: `grounded_plus_web` goes to web,
  `grounded_only` abstains.
- History: Query/Answer records and their entity links are always written (core feature).
  Only answer *reuse* from history is removed; repeat questions are served by the exact cache.
- Web write-back is a worker job; it bumps the owner's index_version after completion.
- Tracing exports to `${LANGFUSE_HOST}/api/public/otel/v1/traces` (default
  https://cloud.langfuse.com) with Basic auth from the Langfuse keys; a no-op when keys are unset.
  Remove the local OTel collector from compose if nothing else uses it.

## Fixes (F1–F4)
- F1 Rerank: as per Decisions. Log timeouts, confirm warmup, report stage timings
  for the 3 baseline doc questions.
- F2 Evidence gate: as per Decisions. Tests: an off-topic question (Tokyo population) against
  isomd goes to web; the 3 baseline doc questions stay on docs.
- F3 Remove history_step reuse; keep records. The slice-2 repeat-question test passes through
  retrieval of ingested web chunks, not history.
- F4 Web context: chunk fetched pages, send only the top 5 chunks by similarity to the LLM.
  Report the stage breakdown for 3 forced-web questions.

## Step 3: Exact answer cache (done)
Key = sha256(owner_id | index_version | PROMPT_VERSION | answer_policy | normalized question).
index_version = per-owner Redis counter, incremented by the worker after index, delete and
web write-back jobs. TTL 24 h; 6 h for web answers. No semantic cache.

## Step 4: Neo4j slimming
1. Chunk↔entity links only in Postgres `entity_mentions` (with `chunk_id`; indexes on
   entity_id and chunk_id).
2. Chunk text in the Qdrant payload with doc_id, owner_user_id, source_kind, title, url.
3. No Chunk nodes in Neo4j. Neo4j keeps:
   - Nodes: Document, Entity, Query, Answer, Message.
   - Edges: Document-[:MENTIONS {count}]->Entity; CO_OCCURS {doc_id, count}; VERSION_OF;
     Query-[:ABOUT]->Entity; Query-[:ANSWERED_BY]->Answer; Answer-[:MENTIONS]->Entity;
     Answer-[:CITES]->Document; Query-[:NEXT]->Query; Message-[:MENTIONS]->Entity.
4. Graph retrieval: entity seeds → Neo4j neighbours (owner filter in Cypher WHERE) →
   chunk ids from Postgres mentions → payloads from Qdrant by point id.
   Same results as the current path.
5. Delete document: Document node, its CO_OCCURS edges, Qdrant points, Postgres mentions
   (cascade), orphan entities (no mentions and no Query/Answer/Message links).
6. Reconciler: per document, compare chunk count + checksum (Postgres vs Qdrant),
   the doc→entity set (Postgres vs Neo4j), and entity ids (Postgres / Neo4j / Qdrant).
   `--dry-run` writes nothing. `--repair` re-queues index jobs for drifted documents.
7. Tests: zero drift after ingest, delete and web write-back; dry-run leaves counts and the
   outbox unchanged; graph retrieval gives the same chunks for a fixed question;
   ACL leak tests pass. Report Neo4j node/edge counts before and after.

## Step 5: Answer metadata
Persist on every Answer: `source` (docs / web / model / abstain), `path` (e.g. docs→web),
`top_score`, `stage_timings_ms`. Show source, path and top score in the Ask UI.
Test: every answer path stores all four fields.

## Step 6: Tracing
One OpenTelemetry span per LangGraph node. LLM spans carry input/output token counts and
`litellm.completion_cost()`. Export per Decisions. Remove any other Langfuse instrumentation.
Test: spans are created per node with a fake exporter; no network when keys are unset.

## Step 7: Graph UI
- Show Document, Entity and Query nodes; no Chunk nodes.
- Clicking an entity shows the chunk texts that mention it (Postgres mentions → Qdrant payloads).
- Clicking a query shows its answer, source and path.
- Filters: source kind (upload / web / chat) and minimum co-occurrence count.
- Frontend lint, typecheck and tests pass.

## Step 8: Final verification
Full suite, plus regression tests for:
- upload < 1 s
- health responsive during ingest
- cache miss after a new upload (index_version)
- repeat web question answered from ingested chunks without a web call
- owner-scope isolation
- grounded_only abstains
- NOT_FOUND → web

Final baseline report against all targets.
