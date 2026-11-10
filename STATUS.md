# STATUS — Step 0 Audit (Handoff)

**Audit date:** 2026-11-07
**Branch:** `features/one`
**HEAD:** `c52a7eb chore: snapshot pre-audit state (handoff-start)`
**Pre-audit tag:** `handoff-start` (points at `c52a7eb`)
**Scope of this document:** independent verification of the running system against the intent in `README.md`. No production code was changed in Step 0. Evidence is command output plus `file:line` references.

> Convention: "proven" means it was reproduced live during this audit. "static" means read from code/config. Anything not reproduced is labelled as such.

---

## 0. Remediation progress (post-audit)

This section tracks the approved remediation sequence. It is appended as items land; the audit
sections below remain the Step 0 evidence.

| Item | Status | Evidence |
| --- | --- | --- |
| 0. Single Docker Postgres + Alembic | **Done** | Docker PG on host `5433`; `make up` port guard; Alembic revision `a9cf8318b733`; clean re-ingest + 0 drift |
| 1. Tooling cleanup | **Done** | `ruff check` + `ruff format` + `mypy` clean; eval writes redirected to temp dirs; `.env.example` updated |
| 2. Eval items 1–5 | **Done** | Grounded 30-row dev/test golden set; chunk-level metrics per category; isolated clean-ingest `make eval`; hermetic gate; 65 tests pass |
| 3. ACL items 7–9 | Pending | — |
| 4. Item 6 honest baseline | Pending | — |
| 5. Items 11–13 | Pending | — |

### Item 0 — one PostgreSQL, one schema authority

**Port split (changed from the original "stop native PG17" plan, at the user's request).** The
Docker Postgres publishes host port **5433** so it can run alongside the native PostgreSQL 17
install that owns 5432. `POSTGRES_PORT` is the single knob and must agree in `.env`,
`infra/docker-compose.yml`, and `backend/app/core/config.py`. This removes the IPv4/IPv6 shadowing
that made clients hit different servers.

Proof:

```text
make up
  Checking PostgreSQL port 5433 for a non-Docker server...
    127.0.0.1:5433 -> free
    ::1:5433 -> free
  OK: no conflicting PostgreSQL server on 5433.
  graphrag-postgres ... 0.0.0.0:5433->5432/tcp, [::]:5433->5432/tcp
```

`make up` still fails closed: `backend/app/tools/preflight_postgres.py` connects to the configured
port and refuses to start if the listener's `data_directory` is not `/var/lib/postgresql/...`
(i.e. not the project's Docker server). Proven against native PG17 on 5432 before the port change.

**Alembic is authoritative.** `backend/alembic/` + `backend/alembic.ini` were added. The initial
migration `a9cf8318b733_initial_schema.py` creates `documents`, `outbox_events`, `spans`,
`threads`, `chunks`, `messages` plus indexes. `make migrate` runs `alembic upgrade head`; `dev`,
`ingest`, and `reconcile` depend on it. `init_db` / `create_all` is now tests-only.

Proof (fresh Docker DB):

```text
make migrate
  Running upgrade  -> a9cf8318b733, initial schema
psql: alembic_version, chunks, documents, messages, outbox_events, spans, threads
version=a9cf8318b733
alembic check -> No new upgrade operations detected.
downgrade base -> upgrade head -> exit 0
```

The app refuses to start without the migration. `backend/app/core/lifecycle.py` calls
`verify_schema`, which checks `to_regclass('public.alembic_version')`; a DB created with
`create_all` (e.g. the old native DB) raises:

```text
verify_schema raised: Database schema is not initialized: table 'alembic_version' is missing.
Run `make migrate` (Alembic) before starting the app, ingestion, or reconciler.
```

**Clean re-ingest into Docker Postgres.** Qdrant collection, Neo4j data, and Redis were reset, then
`make ingest` ran against the migrated Docker DB:

```text
Total Chunks: 45 | Qdrant Vectors: 45 | Neo4j Entity Nodes: 17 | Neo4j Relationship Edges: 95
Outbox Worker processed 60 events successfully.
```

`make reconcile` then reported `45 chunks` in Postgres/Qdrant/Neo4j and **0 missing, 0 ghosts** in
both stores.

**Same resolved database in all three entry points.** The shared helper
`announce_database_identity()` prints the redacted URL and the server identity; the app lifespan,
the ingestion CLI, and the reconciler all call it:

```text
# ingestion CLI
Resolved DATABASE_URL: postgresql+asyncpg://postgres:***@localhost:5433/graphrag_lab
PostgreSQL server: 172.19.0.5:5432 | database=graphrag_lab | data_directory=/var/lib/postgresql/data

# reconciler
Resolved DATABASE_URL: postgresql+asyncpg://postgres:***@localhost:5433/graphrag_lab
PostgreSQL server: 172.19.0.5:5432 | database=graphrag_lab | data_directory=/var/lib/postgresql/data

# app lifespan
Resolved DATABASE_URL: postgresql+asyncpg://postgres:***@localhost:5433/graphrag_lab
PostgreSQL server: 172.19.0.5:5432 | database=graphrag_lab | data_directory=/var/lib/postgresql/data
```

`README.md` now documents the port split, the preflight guard, and the bring-up order.

### Item 1 — tooling cleanup and hermetic test output

**Lint, format, and types are clean.** `ruff check app tests`, `ruff format app tests`, and
`mypy app tests` all pass with no errors (114 source files). The auto-fixes were import ordering,
unused-import removal, and line wrapping; `git diff -w` shows no behavior changes.

```text
uv run --directory backend ruff check app tests   -> All checks passed!
uv run --directory backend ruff format app tests  -> 23 files reformatted, 91 left unchanged
uv run --directory backend mypy app tests         -> Success: no issues found in 114 source files
```

**Tests no longer write tracked eval files.** `backend/tests/conftest.py` now points
`EVAL_GOLDEN_DIR` at a temp dir seeded with copies of `questions.jsonl` / `multi_turn.jsonl`, and
`EVAL_CANDIDATES_DIR` at a fresh temp dir, before importing `app.main`. `evals.py` and `threads.py`
resolve their paths from those settings. `.env.example` documents both variables (blank = repo
defaults).

Proof:

```text
SHA256 before = B289709FB1E2ED52AEB5EB9A6A019FF2DEB46837E0250FED6AF53E28423AEDAB
pytest tests/unit/test_threads_api.py -> 1 passed
SHA256 after  = B289709FB1E2ED52AEB5EB9A6A019FF2DEB46837E0250FED6AF53E28423AEDAB
UNCHANGED = True
temp output: C:\Users\mahil\AppData\Local\Temp\graphrag-candidates-9syn1ml8\golden_candidates.jsonl
```

After the full suite, `git status --short evals/` is empty and all three golden/candidate hashes are
unchanged.

**Full suite (Docker Postgres on 5433).** 64 tests collected, **63 passed, 1 failed**. The single
failure is `test_three_turn_thread_pronoun_resolution_and_traces`, a live-LLM test that asserts the
model's query rewrite removes "they"; the model returned
`"How did they fix the outbox service deserialization error during deployment v2.4.1?"`, which keeps
the pronoun. This is live-model nondeterminism, not a tooling regression. It is intentionally
deferred to item 2, which marks live-LLM tests `@pytest.mark.live` and excludes them by default
after building the hermetic fake.

> Note: the harness process environment sets `POSTGRES_PORT=5432` (native PG17). Clear
> `POSTGRES_*` before verification runs so the `.env` values for Docker on 5433 win:
> `Remove-Item Env:POSTGRES_PORT,Env:POSTGRES_DB,Env:POSTGRES_USER,Env:POSTGRES_PASSWORD,Env:POSTGRES_HOST`.

---

### Item 2 — evaluation items 1–5 (honest measurement machinery)

Scope delivered: (1) isolated clean ingest + `make eval`; (2) real chunk ids and chunk-level
recall/precision/nDCG/MRR per category in the API and CI; (3) dev/test split; (4) hermetic tests
with a model fake and `LIVE_LLM=1` opt-in; (5) `multi_turn.jsonl` included and every golden
`expected_chunk_ids` asserted to exist after ingest. No thresholds were tuned.

**Golden data is grounded in the corpus, not fabricated.** `evals/golden/questions.jsonl` has 20
rows (10 dev / 10 test) and `multi_turn.jsonl` has 10 rows (5 dev / 5 test). Every
`expected_chunk_ids` value is a real chunk id produced by `parse_markdown` +
`chunk_parsed_document` over `corpus/`. `evals/golden/README.md` documents the split, provenance,
chunk-id format (`chk_{doc_id}_{index:04d}_{sha256(text)[:10]}`), dependency rules, and non-goals.

**The dataset model understands splits and dependencies.** `backend/app/evaluation/datasets.py`
adds `split`, `depends_on`, `load_from_dir`, `filter_by_split`, `missing_chunk_ids`, `splits`, and
`split_summary`. Paraphrase rows declare the parent they paraphrase; the runner executes the parent
first in the same orchestrator so the cache is populated naturally and never pre-seeded.

**The runner reports chunk-level IR metrics per category.** `backend/app/evaluation/runner.py`
reports `chunk_recall@1/3/5`, `chunk_precision@1`, `chunk_ndcg@5/10`, `chunk_mrr`,
`chunk_hit_rate@5`, `doc_recall@3`, `doc_ndcg@10`, `doc_mrr`, plus operational latency/cost,
cache-hit, abstention, citation validity, and multi-turn rewrite accuracy. Concurrency defaults to
`EVAL_CONCURRENCY=2`, questions run in dependency waves, and the run is capped by
`LLM_MAX_BUDGET_PER_RUN` with total cost reported.

**The gateway is resilient and cheap to re-run.** `backend/app/llm/gateway.py` adds exponential
backoff with jitter for 429/5xx/timeout, an on-disk cache keyed by model/prompt/system/max_tokens/
temperature, a per-run budget, and `reset_usage()`. Cache hits cost `$0` in the run and are
reported as `cached=True`; the stored original cost is preserved in the cache file only.

**Tests are hermetic and live calls are opt-in.** `backend/tests/fakes/fake_gateway.py` synthesizes
deterministic cited answers from the wrapped `<source_chunk>` context; `backend/tests/fakes/hermetic.py`
reproduces the 15-document / 45-chunk corpus in memory; `backend/tests/fakes/in_memory_cache.py`
now uses embedding similarity plus `validate_cache_hit`. `backend/pyproject.toml` sets
`addopts = "-q -m 'not live'"` and registers the `live` marker, so `pytest -m live` is the only way
to hit a provider. `backend/tests/conftest.py` sets `APP_ENV=test`, `GEMINI_API_KEY=""`, a temp
`LLM_CACHE_DIR`, and temp golden/candidate dirs before importing the app.

**`make eval` runs a clean, isolated ingest.** `backend/app/tools/eval_cli.py` overrides
`POSTGRES_DB`/`QDRANT_COLLECTION` from `EVAL_POSTGRES_DB`/`EVAL_QDRANT_COLLECTION` before importing
app modules, refuses to run if either resolves to the developer store, recreates the eval database,
applies Alembic, resets the eval Qdrant collection, ingests the corpus, drains the outbox, verifies
counts, validates every golden chunk id, clears both caches, and scores the requested split.

Honest live baseline (`make eval`, test split, first run, cache empty):

```text
Eval PostgreSQL database: graphrag_lab_eval
Eval Qdrant collection:   grant_chunks_eval
Recreated eval database 'graphrag_lab_eval'.
Reset eval Qdrant collection 'grant_chunks_eval'.
Resolved DATABASE_URL: postgresql+asyncpg://postgres:***@localhost:5433/graphrag_lab_eval
PostgreSQL server: 172.19.0.5:5432 | database=graphrag_lab_eval | data_directory=/var/lib/postgresql/data
Ingested 15 documents; outbox processed 60 events.
PostgreSQL documents: 15
PostgreSQL chunks:    45
Qdrant vectors:       45
Golden dataset: 30 rows ({'dev': 15, 'test': 15, 'total': 30}), categories=['fact', 'global', 'multi_hop', 'multi_turn', 'paraphrase', 'unanswerable']

Golden evaluation report (split=test)
Questions:        15
Router accuracy:  0.6667
Cache hit rate:   0.1333
Total cost:       $0.005414 / budget $0.5000

category       n  chunk_r@5  chunk_ndcg@10  chunk_mrr   hit@5  doc_ndcg@10  latency_ms  cost_usd
fact           3      1.000          0.877      0.833   1.000        0.877      9092.8  0.000400
global         1      1.000          1.000      1.000   1.000        1.000     10288.1  0.000700
multi_hop      2      1.000          0.597      0.417   1.000        0.693      8459.1  0.000400
multi_turn     5      0.700          0.514      0.467   0.800        0.984     22152.9  0.000500
paraphrase     2      1.000          0.816      0.750   1.000        0.816        28.4  0.000000
unanswerable   2      1.000          1.000      1.000   1.000        1.000         3.2  0.000000
```

Safety/structural values from the same run: `unanswerable.abstention_rate = 1.0`,
`paraphrase.cache_hit_rate = 1.0` (both test paraphrases hit the naturally-populated cache),
`multi_turn.rewrite_accuracy = 0.8`. Re-running `make eval` with the cache warm costs `$0.000000`
and drops per-question latency to sub-second, proving the disk cache works. The ~9s single-turn
latency seen here is the already-tracked known issue; it is not optimized in this item.

**Verification:**

```text
uv run --directory backend ruff check app tests   -> All checks passed!
uv run --directory backend ruff format app tests  -> 117 files left unchanged
uv run --directory backend mypy app tests         -> Success: no issues found in 117 source files
uv run --directory backend pytest                 -> 65 passed in 7.53s
pytest tests/eval_gate/test_eval_gate.py -s -v    -> 2 passed in 0.22s
```

The CI gate is hermetic and asserts structure, not tuned quality: all 30 rows load, the split is
15/15, all six categories are present, every `expected_chunk_ids` exists, `multi_turn.jsonl` is
included, paraphrase rows have `depends_on`, caches start empty, chunk-level metrics exist per
category, `unanswerable.abstention_rate == 1.0`, and `multi_turn.rewrite_accuracy >= 0.8`.

Hermeticity proof: after the full suite and live `make eval`, the tracked candidate file is
unchanged (`SHA256 B289709FB1E2ED52AEB5EB9A6A019FF2DEB46837E0250FED6AF53E28423AEDAB`), and
`git status --short evals/` shows only the intentional golden edits. Eval output goes to the temp
JSON path when requested, and the LLM cache lives in gitignored `.llm_cache/`.

> Known and deliberately not tuned here: router accuracy `0.6667`, multi-hop `chunk_ndcg@10 0.597`,
> and multi-turn `rewrite_accuracy 0.8` are the honest baseline for item 6.

---

## 1. Repo hygiene and secrets

| Check | Result | Proof |
| --- | --- | --- |
| `.env` ignored | Yes | `git check-ignore -v .env backend/.env` → `.gitignore:16:.env` |
| Dev env files ignored | Yes | `git check-ignore -v frontend/.env.development` → `.gitignore:17:.env.*` |
| `.env` ever committed | **No** | `git log --all --oneline -- .env backend/.env` → empty |
| Tracked env files | Only `.env.example` | `git ls-files \| Select-String '(^\|/)\.env'` |
| `.env.example` secrets | Blank placeholders | `.env.example:32` `GEMINI_API_KEY=`, `:39-40` Langfuse keys blank |
| Working tree | Clean after restoring test side-effect | `git status --short` → empty |
| Snapshot commit | 245 files / 43,772 insertions | `git show --stat c52a7eb` |
| Tag | `handoff-start` exists | `git tag --list` |

`.gitignore` covers `__pycache__/`, `.venv/`, `node_modules/`, `frontend/dist/`, `*.db`, `*.sqlite*`, `.env*` (with `!.env.example`), and model caches (`fastembed_cache/`, `hf_cache/`, `.cache/`, `*.onnx`, `*.safetensors`).

**Leaked credentials:** `.env` contains non-empty Gemini and Langfuse keys (lengths 53 / 44 / 44). They were never committed, but they were used in this session's live calls and must still be rotated. The user has confirmed rotation is in progress.

**Test side-effect (fixed):** running the test suite appended generated rows to `evals/candidates/golden_candidates.jsonl` (5 lines). Source: `backend/app/api/routes/threads.py:657-659` writes candidate pairs into a tracked data file. Reverted with `git restore`; this is recorded as a non-hermetic test defect.

---

## 2. Environment topology — resolving "45 rows vs empty Postgres"

This was the first blocker. **There are two PostgreSQL servers.** The application talks to the native one; the Docker one is a decoy.

| Store | Container / process | Endpoint | Used by app? |
| --- | --- | --- | --- |
| PostgreSQL | **native PostgreSQL 17**, PID 7644, data dir `C:/Program Files/PostgreSQL/17/data`, service `postgresql-x64-17` | `0.0.0.0:5432` (IPv4) | **Yes** |
| PostgreSQL (Docker) | `graphrag-postgres` (`postgres:16-alpine`) | published `5432`, real listener is Docker backend PID 6076 on IPv6 `::` | No — DB has **0 tables** |
| Qdrant | `graphrag-qdrant` (`qdrant/qdrant:v1.13.2`) | `6333/6334` | Yes |
| Neo4j | `graphrag-neo4j` (`neo4j:5.26-community`) | `7687` | Yes |
| Redis | `graphrag-redis` (`redis:7-alpine`) | `6379` | Yes |

Proof:

```text
PostgreSQL (Source of Truth): 45 chunks     # reconciler, via app engine
server: ('graphrag_lab', 'postgres', 'C:/Program Files/PostgreSQL/17/data', 5432)
docker exec graphrag-postgres psql ... -> /var/lib/postgresql/data, 0 public tables
```

All three app entry points resolve to the same URL `postgresql+asyncpg://postgres:***@localhost:5432/graphrag_lab`:

- app: `backend/app/db/postgres.py` (`get_engine`)
- ingestion CLI: `backend/app/ingestion/cli.py`
- reconciler: `backend/app/indexing/reconciler.py`

**Implication:** `docker exec graphrag-postgres psql` will always show an empty DB. Never use the Docker Postgres for counts. A later step should either remove the port collision or make the compose DB the only DB, and document it.

**Related inconsistency:** golden answers say "PostgreSQL 16" while the live source of truth is PostgreSQL **17**.

---

## 3. Pipeline reality check (live)

`make ingest` was run against native PG17, then the reconciler.

### 3.1 Ingestion

Corpus on disk: 13 top-level `.md` + 3 under `corpus/adversarial/` = 16 files. `corpus/README.md` is skipped (`backend/app/ingestion/cli.py:35-36`); the 3 adversarial docs are ingested in a second loop (`cli.py:52-62`). Result: **15 documents / 45 chunks**.

### 3.2 Post-ingest counts (native PG17)

```text
documents: 15
chunks: 45
outbox_events: 180   (all PROCESSED)
threads: 0
messages: 0
spans: 341
duplicate (doc_id, chunk_id): []
```

### 3.3 Downstream stores

```text
Qdrant: 45 points, 47 indexed_vectors_count
Neo4j:  45 Chunk, 17 Entity
        83 MENTIONS, 5 OWNED_BY, 4 LED_BY, 1 STAGED_IN, 1 IMPACTED, 1 COMMANDED (95 edges)

Reconciler:
  PostgreSQL (Source of Truth): 45 chunks
  Qdrant Vector Store:         45 chunks
  Neo4j Knowledge Graph:       45 chunks
  Missing in Qdrant: 0 | Missing in Neo4j: 0 | Ghost in Qdrant: 0 | Ghost in Neo4j: 0
  [SUCCESS] 100% synchronization. Zero drift detected.
```

### 3.4 Defect: re-ingest is not idempotent at the outbox level

`outbox_events = 180` after ~3 ingestion runs of 60 events. `make ingest` re-adds outbox events for already-ingested chunks instead of skipping unchanged content (`content_hash` is not used to suppress re-index events). Chunk/doc rows do not duplicate, but the event log grows on every run. This must be fixed before "reproducible ingest" can be claimed.

### 3.5 Definition-of-done gap

`make up && make ingest && make eval` — **`make eval` does not exist**. `Makefile` targets are `ingest`, `worker`, `reconcile`, `test-int`, `test-gate`, plus dev/lint/format/typecheck/check/up/down/logs/ps/clean. The eval gate only runs as a pytest test.

---

## 4. Live API evidence

Backend served on `127.0.0.1:8000`. Auth is the `X-Dev-User` header (`backend/app/core/auth.py`).

### 4.1 Health

```text
GET /api/v1/health -> 200
{"status":"ok","components":{"postgres":"healthy","qdrant":"healthy","neo4j":"healthy",
 "redis":"healthy","outbox":"healthy"},"outbox_lag":0}
```

### 4.2 Query — bob, explicit `scope=sre` (the happy path)

`POST /api/v1/query` with `{"query":"Why did the cache stampede happen during the incident, and what mitigation was proposed?","scope":"sre"}`

```text
HTTP 200 in 9.95s
strategy=vector, cached=false, abstention=false, cost_usd=0.000928, latency_ms=9945
evidence: real chunk ids from doc_postmortem_inc_04 and doc_cache_stampede_mitigation
answer: correct synthesis with inline citations
```

This is a genuine end-to-end result: real retrieval, real rerank, real Gemini generation, real cost.

### 4.3 Query — alice / `public` (no leak to public scope, but abstains)

Same question as alice with `scope=public`:

```text
HTTP 200 in 5.96s
evidence: only doc_adv_01_ignore (public adversarial doc), score -11.31
answer: "I do not have sufficient information..."
```

All non-adversarial corpus docs are non-public, so a public-only user correctly sees nothing relevant. This also exposes a design problem: the **only public corpus is adversarial**, so public-scope retrieval is a prompt-injection test by default.

### 4.4 Query — bob with **no** scope (default-scope bug)

```text
HTTP 200 in 3.31s
evidence: only doc_adv_01_ignore
```

Bob should default to `sre`, but he gets `public`. Root cause proven by repeatedly constructing users:

```text
bob  | allowed_scopes=['public','sre'] | default scope= is_public=True, roles=(), groups=()
dave | allowed_scopes=['core-banking','public'] | default scope= is_public=True
```

`backend/app/core/auth.py:32`:

```python
"data-platform" if "data-platform" in self.allowed_scopes else list(self.allowed_scopes)[0]
```

`allowed_scopes` is a `set` (`auth.py:14`), so the fallback is a non-deterministic choice. Bob/dave can lose all non-public privileges depending on set iteration order. `alice`, `elena`, `auditor`, `admin` happen to survive because `data-platform` is special-cased or they have it.

### 4.5 ACL leak — **graph route returns restricted documents to bob**

Query: `"Who leads the engineering team that owns the database where the outbox writes?"`, bob, `scope=sre`.

Bob can legitimately see only: `doc_adv_01/02/03`, `doc_cache_stampede_mitigation`, `doc_postmortem_inc_04`, `doc_redis_sentinel_failover`.

Actual response:

```text
HTTP 200 in 11.01s, strategy=graph
answer cites: doc_team_directory_2026, doc_rfc_001, doc_rfc_004  (all data-platform only)
also returns:  doc_postmortem_inc_04                      (legitimately sre)
```

**This is a real cross-tenant ACL leak through the graph path.** The answer discloses the Data Platform Team lead and storage architecture to an SRE user.

#### Root cause

- `backend/app/graph/retrievers.py:105-108` filters **only** `executive-audit`:

  ```python
  if "executive-audit" in scope_raw and not bool(filter_criteria.user_roles & {"executive-audit"}):
  ```

  Every other role/group is admitted.

- `RetrievalFilter.to_cypher_clause` (`backend/app/retrieval/filters.py:76-89`) *would* be the right mechanism, but it is **never called anywhere in `backend/app`** (only definition found). Its logic is also too weak: `(n.is_public = true OR n.tenant_id = 'default')`, i.e. same-tenant means visible.

- Neo4j itself proves the leak: `Entity` and `Chunk` nodes carry `acl_scope` JSON (e.g. Data Platform Team = `allowed_roles:["data-platform"]`), so the data is present and simply not enforced in Cypher.

### 4.6 `/api/v1/retrieval/compare` has no auth or ACL at all

`backend/app/api/routes/retrieval.py:17-23` accepts `query`, `k`, cutoffs and returns candidates. There is no `get_current_user` dependency and no filter passed to dense/sparse retrieval.

Live request without any header:

```text
GET /api/v1/retrieval/compare?query=Transactional%20Outbox%20postgres%20failure&k=60
total_candidates = 18
documents returned include doc_core_banking_v2, doc_team_directory_2026, doc_rfc_001, ...
```

Any anonymous caller can read restricted content through this endpoint.

### 4.7 `/api/v1/graph?scope=sre` — weak ACL + fabricated analytics

Live response: **17/17 entities**, including Data Platform Team, Payments Team, Elena Rostova, PaymentGateway. The only ACL clause excludes `executive-audit` (`backend/app/api/routes/graph.py:44`).

The same endpoint hardcodes graph analytics:

| Field | Value | Line |
| --- | --- | --- |
| `pagerank` | `0.08` / `0.15` / `0.06` | `graph.py:59,132,159` |
| `degree` | `2` / `4` / `1` | `graph.py:66,133,160` |
| `community` | `0` | `graph.py:60` |
| `cluster` | `"core"` | `graph.py` node construction |
| `tx_time` | fixed timestamp | `graph.py` |
| `chunk_hash` | fabricated | `graph.py` |

These are rendered by the UI as if they were computed graph metrics.

---

## 5. Retrieval / ACL architecture gaps (static + live)

1. **ACL is post-filter, not in-query.** `DenseRetriever` and `BM25Retriever` retrieve `3× top_k` then filter in Python (`backend/app/retrieval/dense.py`, `sparse.py`, `filters.py`). At small corpus size this looks fine; at scale it silently reduces recall and is not a security boundary.
2. **The Cypher filter that exists is unused** and semantically wrong (same-tenant = allowed), see §4.5.
3. **Graph path never applies chunk filtering.** `retrieve_path_evidence` returns `acl_scope` in the row but does not evaluate it (`retrievers.py:101-120`).
4. **Cache ACL check is weaker than it looks.** Semantic cache filters by tenant + entry ACL (`backend/app/cache/semantic.py:124-141`), but the cache key is `sem:{hash(query)}` (`semantic.py:217`), using Python's per-process randomized `hash()`. It does **not** include `prompt_version`, `as_of`, or index version in the key. Exact cache does include ACL/index/prompt (`backend/app/cache/keys.py`).
5. **`CACHE_INVALIDATED` is a no-op** (`backend/app/indexing/outbox_worker.py:91-92`), so deleting/updating a doc never invalidates cached answers.

---

## 6. Evaluation validity — the gate cannot pass honestly

This is the largest correctness problem in the repo. The CI gate is green for the wrong reasons.

### 6.1 The gate never ingests and never uses real chunk ids

`backend/tests/eval_gate/test_eval_gate.py:11-22` builds an **in-memory SQLite** DB with empty tables. It asserts only dataset length and thresholds; it never runs `make ingest` and never checks that retrieved chunk ids exist.

`EvaluationRunner.setup_corpus_and_orchestrator(session, corpus_dir)` (`backend/app/evaluation/runner.py:41-83`) **ignores both arguments**. It only clears caches and returns an orchestrator.

### 6.2 The gate pre-seeds the cache with the answer

`runner.py:55-75` pre-warms the exact and semantic cache for `q_parent_3 = "When was incident INC-2026-04?"` with a fully-formed `Answer` (including evidence chunk `chk_postmortem_inc_2026_04_01`). The paraphrase/cache threshold then passes because the answer was planted, not because retrieval/caching worked.

### 6.3 Golden `expected_chunk_ids` are fabricated

```text
questions: 20
distinct expected_chunk_ids: 10
distinct expected_doc_ids: 4
expected_chunk_ids not present in chunks: 10 / 10
examples: chunk_storage_overview_01, chunk_inc04_root_cause_02, chunk_team_data_01, ...
```

Every expected chunk id in `evals/golden/questions.jsonl` is invented; none exists in the real `chunks` table. The runner never reads `expected_chunk_ids` anyway — it scores only doc-level recall/precision/nDCG/MRR (`runner.py:155-168`). So "retrieval quality" is doc-level only, and the chunk ground truth is decorative.

### 6.4 No train/test split, no category reporting in the API, admin scope everywhere

- The same 20 questions are used for tuning and gating; there is no dev/test split.
- The API gate returns only `accuracy` (`backend/app/api/routes/evals.py:109-116`), not per-category metrics.
- Every benchmark question runs with a synthetic **admin** scope (`runner.py:100-103`), so ACL correctness is not measured at all.

### 6.5 Gate thresholds

`test_eval_gate.py:54-78` asserts router accuracy ≥ 0.85, unanswerable abstention == 1.0, fact Recall@1 ≥ 0.80, fact nDCG@1 ≥ 0.80, multi-hop Recall@3 ≥ 0.80, cache hit ≥ 0.80 — all against the seeded/empty environment above.

### 6.6 `multi_turn.jsonl` is excluded

`evals/golden/multi_turn.jsonl` has 10 rows and is not loaded by the gate or `make test`.

### 6.7 Non-hermetic tests

`uv run --directory backend pytest` → **5 failed, 59 passed in 397.87s**. All five failures are live Gemini calls:

```text
litellm.RateLimitError: 429 (daily quota) / litellm.APIConnectionError
tests/eval_gate/test_eval_gate.py::test_golden_benchmark_ci_eval_gate
tests/integration/test_vertical_slice.py::test_acl_leak_protection
tests/integration/test_vertical_slice.py::test_temporal_as_of_filtering
tests/unit/test_orchestration.py::test_orchestrator_vector_fact_execution
tests/unit/test_orchestration.py::test_orchestrator_graph...
```

Unit/integration/gate tests call the real model gateway; there is no hermetic model fake. This also means the suite depends on external quota and writes to tracked files.

---

## 7. PostgreSQL as source of truth — gaps

| Requirement (README #4) | Current state | Evidence |
| --- | --- | --- |
| Postgres owns doc/chunk/version/ACL | Yes at rest | `documents`/`chunks` tables |
| Schema created before ingest | **No** | `init_db` is only called from app lifespan (`backend/app/core/lifecycle.py:37`); `ingestion/cli.py` and `indexing/reconciler.py` never call it |
| Alembic migrations | **None** | no `alembic.ini`, no `migrations/`; schema is `Base.metadata.create_all` (`backend/app/db/postgres.py:75-79`) |
| Writes go through outbox in the same transaction | Partially | outbox rows exist, but see §3.4 non-idempotent re-ingest |
| Indexers idempotent | Upserts yes, outbox growth no | §3.4 |
| Reconciler diffs Postgres vs Qdrant vs Neo4j | Yes, same DB | live 0 drift |
| Cache invalidation driven by outbox | **No** | `CACHE_INVALIDATED` handler is `pass` (`outbox_worker.py:91-92`) |

Consequence: a fresh clone can start the API (which creates tables) but `make ingest` alone does not guarantee schema existence. There is no migration path for schema changes.

---

## 8. Verified deletes — not verified

`DELETE /api/v1/documents/{id}` (`backend/app/api/routes/documents.py:150-165`) deletes only the Postgres row via `DocumentRepository.delete_document`, stages a delete event, drains the outbox, and then **unconditionally** returns:

```python
stores_cleared=["PostgreSQL", "Qdrant", "Neo4j", "Redis"]
```

There is no post-delete count check in Qdrant, Neo4j, or Redis, and `CACHE_INVALIDATED` does nothing, so Redis is never touched. The Definition of Done requirement "deleting a document removes it from Qdrant, Neo4j and the cache (reconciler clean)" cannot currently be demonstrated. No live delete was run during Step 0 (would mutate the demo corpus); this is a static finding, flagged for the delete step.

---

## 9. Hardcoded / fabricated value inventory

### 9.1 Backend

| Surface | Behavior | Location |
| --- | --- | --- |
| `GET /cache/stats` | Fixed `42` requests, `0.64` hit rate, `184.5` p95, fixed series | `backend/app/api/routes/cache.py:26-36` |
| `GET /cache/invalidations` | Reads real outbox, but `affected_keys_count=1` and `acl_scope="data-platform"` are fabricated | `cache.py:52-64` |
| `GET /metrics/overview` | Counts are real; `golden_set_accuracy=0.94`, `p95_latency_ms=142`, `cache_hit_rate=0.64`, `cost_per_correct_answer_usd=0.00018`, `unverified_facts_pending=0` are fixed | `metrics.py:48-53` |
| `GET /metrics/guardrails` | All fixed: `prompt_injection_attempts=3`, `faithfulness_gate_rejections=1`, `hallucination_eval_score=0.98`, `pass_rate=0.96` | `metrics.py:16-22` |
| `GET/PUT /experiments` | Fixed in-memory list; mutations lost on restart | `backend/app/api/routes/experiments.py:7-34` |
| `GET /settings` | Store health is real; `default_as_of_date="2026-04-12"`, theme and latencies are in-memory | `settings.py:15-18` |
| `GET /traces` | Span-only traces get `tokens=120`, `cost_usd=0.00003`; message-backed traces use real values | `traces.py:85-86` |
| `GET /graph` | `pagerank`, `degree`, `community`, `cluster`, `tx_time`, `chunk_hash` fixed | `graph.py:59-66,132-133,159-160` |
| `GET /retrieval/compare` | No auth/ACL; default query is hardcoded | `retrieval.py:17-23` |
| `Answer` / traces | Tracer writes `start_time == end_time` for every span and passes empty `query`/`route` attributes (`backend/app/observability/tracer.py:51-74`); `spans` has no `status` column, only `status_code` | proven by querying `spans` |
| Cache key | `sem:{hash(query)}` — process-randomized, no prompt version / as-of / index version | `backend/app/cache/semantic.py:217` |

### 9.2 Frontend

MSW is **on by default**, including production builds:

- `frontend/src/mocks/browser.ts:7` → `const mode = import.meta.env.VITE_API_MODE ?? "mock";`
- `frontend/src/main.tsx:5-8` always calls `enableMocking()`
- `frontend/.env.development` → `VITE_API_MODE=mock`

So unless `VITE_API_MODE` is explicitly set to a non-`mock` value at build time, **every page reads fixtures**, not the backend.

| Page | Data path | Verdict |
| --- | --- | --- |
| Ask | `useThreads`, `useGraph` hooks | Real hooks, but MSW intercepts in default mode |
| Overview | `useOverviewMetrics` | Real hook (serves partly-hardcoded backend values) |
| Documents | `useDocuments` | Real hook |
| Graph | `useGraph` | Real hook (serves fabricated metrics) |
| Traces | `useTraces` | Real hook |
| Retrieval | `useRetrievalCompare` | Real hook, but hardcoded query default |
| Cache | `useCacheStats` | Real hook (serves hardcoded stats) |
| Settings | `useSettings` | Real hook (serves in-memory settings) |
| Experiments | local `DEFAULT_RUNS` | **Fabricated**, rendered unconditionally at `ExperimentsPage.tsx:272` |
| Golden Set | `useGoldenDataset` + local eval report | **Fabricated** pass/faithfulness; always reports PASSED in `onSuccess` (`GoldenSetPage.tsx:72-83`), initial report `60/60`, `0.958`, `395ms` (`:54-61`), per-row `lastAccuracy:"pass"`, `faithfulness:0.96`, `320ms` (`:38-40`) |

Other frontend hardcodes:

- `RetrievalPage.tsx:35` selected candidate `"chunk-4"`; `:38` fixed query `"Transactional Outbox postgres failure"`; `:50-55` fake rank defaults `|| 1`.
- `GraphPage.tsx:42` `asOfDate = "2026-04-12"`.
- `AskPage.tsx:540` score fallback `"0.94"`.
- `AppContext.tsx:27-33` all-healthy defaults (`1.2/2.4/3.1/0.8ms`); `:53-54` `aclScope="data-platform"` and `asOfDate="2026-04-12"`; `:120` falls back to healthy on backend error.

---

## 10. Tooling baseline

Backend:

| Check | Result |
| --- | --- |
| `uv run --directory backend pytest` | **5 failed, 59 passed in 397.87s** (all 5 are live Gemini 429/connection) |
| `uv run --directory backend ruff check app tests` | **11 errors**: `I001` ×6, `F401` ×3, `F541` ×1, `F841` ×1 |
| `ruff format --check app tests` | **26 files would be reformatted** |
| `mypy app tests` | **7 errors**, all real-vs-fake type mismatches in `tests/unit/test_outbox_worker.py` (6) and `tests/unit/test_orchestration.py` (2) |

Frontend:

| Check | Result |
| --- | --- |
| `npm run lint` (`tsc --noEmit`) | **PASS** (exit 0) |
| `npm test` (`vitest run`) | **PASS** (1 file, 18 tests, 11.25s); noisy `HTMLCanvasElement.getContext()` warnings because `canvas` is not installed |
| `npm run build` | **PASS** (1.85s); warns `index` 880 kB and `GraphCanvas3D` 1,349 kB chunks > 500 kB |

---

## 11. Definition-of-done checklist (README lines 303-316)

| # | Requirement | Status | Evidence |
| --- | --- | --- | --- |
| 1 | `make up && make ingest && make eval` from clean clone | **FAIL** | `make eval` target missing; schema init not in ingest |
| 2 | One trace per request with per-stage latency/tokens/cost | **FAIL** | spans all share one timestamp; `query`/`route` empty; span-only tokens/cost fixed |
| 3 | Golden scores per category + CI gate blocks regressions | **FAIL** | gate never ingests, pre-seeds cache, 10/10 chunk ids fake, admin scope only |
| 4 | Hybrid beats dense on nDCG@10 | **UNMEASURED** | no honest baseline exists yet |
| 5 | Graph wins multi-hop without losing facts | **UNMEASURED** + current graph leaks ACL | §4.5 |
| 6 | Delete removes doc from Qdrant/Neo4j/cache | **FAIL** | §8 |
| 7 | Zero ACL leaks; injection rate measured | **FAIL** | §4.5, §4.6; adversarial docs present but success rate not measured |
| 8 | Cache wrong-hit rate measured and bounded | **FAIL** | `/cache/stats` fixed; semantic key unstable; invalidation no-op |
| 9 | MS GraphRAG and LightRAG baselines compared | **MISSING** | no runners in `benchmarks/` |
| 10 | Experiment write-ups in `docs/experiments/` | **MISSING** | directory absent |

---

## 12. Proposed sequence after Step 0 (for approval)

The user's priorities are front-loaded. Each item is a small, independently verifiable commit with tests.

### Step 1 — Make evaluation honest (blocks everything else)

1. **Isolated clean ingest + `make eval`.** Add `make eval`; create a dedicated eval DB/collection or reset+ingest a fixed corpus into an ephemeral namespace; fail if counts ≠ expected. No cache pre-seeding (`runner.py:55-75` removed).
2. **Real chunk ids and chunk-level metrics.** Regenerate `expected_chunk_ids` from actual `chunks` (or score only on ids that exist); report recall/precision/nDCG/MRR at chunk level, per category, in the API and CI.
3. **Dev/test split.** Split golden set into `dev` (tuning) and `test` (gate only); never tune on test. Record split in `evals/golden/`.
4. **Hermetic tests.** Add a model fake under `tests/fakes/`; default pytest to fake gateway, opt-in `LIVE_LLM=1` for live. Gate must not require network/quota.
5. **Remove `multi_turn.jsonl` exclusion** and assert every golden row's `expected_chunk_ids` exist after ingest.
6. **Report baseline honestly** (even if scores are low). No thresholds raised until the pipeline is real.

### Step 2 — Make ACL a query-time invariant + Postgres source of truth

7. **ACL inside retrieval.** Pass ACL into Qdrant payload filters (`acl_is_public`, `acl_allowed_roles`, `acl_allowed_groups`, tenant, temporal) instead of over-fetch-then-filter. Add leak tests that assert zero restricted ids in ranked output **and** in graph paths.
8. **ACL inside Cypher.** Implement role/group/tenant predicates in `MATCH`/`WHERE` for `Entity`, `Chunk`, and traversed edges; delete the `executive-audit`-only special case; enforce the same predicate in `/api/v1/retrieval/compare`.
9. **Fix default scope.** Derive a deterministic primary scope (explicit order, not `set[0]`); add tests for bob/dave/all users.
10. **Schema + migrations before ingest.** Add Alembic; call `upgrade head` from app startup, ingestion CLI, and reconciler; remove implicit `create_all` reliance.
11. **Outbox-first + idempotent ingest.** Suppress re-index events for unchanged `content_hash`; reconcile outbox growth; make `CACHE_INVALIDATED` actually delete affected cache keys (exact + semantic), and key semantic cache on `(normalized query, tenant, roles, groups, index_version, prompt_version, as_of)`.
12. **Verified deletes.** After delete, assert row counts drop in PG/Qdrant/Neo4j, cache keys gone, reconciler reports zero ghosts; return per-store results, not a fixed list.
13. **Replace hardcoded surfaces.** Either compute (`cache/stats`, `metrics/guardrails`, experiments, settings, trace tokens/cost, graph pagerank/degree/community) or return `501 Not Implemented`. Frontend: disable MSW by default, remove `DEFAULT_RUNS`/fake PASSED eval state, wire real endpoints, show empty/error states.

### Suggested commit order (one item each)

`eval/make-eval` → `eval/real-chunk-ids` → `eval/dev-test-split` → `tests/hermetic-model` → `acl/qdrant-filters` → `acl/cypher-filters` → `acl/default-scope` → `db/alembic` → `outbox/idempotent` → `cache/invalidation` → `delete/verified` → `api/no-fakes` → `frontend/live-mode`

### Explicit non-goals for Step 1

- No threshold tuning to make the gate green.
- No new UI features.
- No new retrieval algorithms until the baseline is honest.

---

## 13. Known issues (tracked, not yet fixed)

- **Query latency: ~9.9 s end-to-end** for the live `bob`/`scope=sre` answer (measured in Step 0,
  §4.2). This is recorded, not optimized. Once tracing is real (per-stage spans with independent
  timestamps), break the 9.9 s down by route, dense retrieval, sparse retrieval, graph traversal,
  rerank, cache lookup, LLM generation, and serialization, then decide what to fix. Do not tune
  latency before the baseline is honest.
- **Docker Postgres host port is 5433**, while the native PostgreSQL 17 install may still own 5432.
  This is intentional (coexistence). Any client that hardcodes 5432 is talking to the native
  server, not the project database. `POSTGRES_PORT` is the single source of truth.

---

## Appendix A — Reproduction commands

```powershell
# Repo state
git log --oneline -3
git tag --list
git status --short
git check-ignore -v .env backend/.env frontend/.env.development
git ls-files | Select-String '(^|/)\.env'
git log --all --oneline -- .env backend/.env

# Infra / DB identity
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Ports}}"
Get-NetTCPConnection -LocalPort 5432 -State Listen
uv run --directory backend python -m app.indexing.reconciler

# Ingestion + stores
make ingest
docker exec graphrag-neo4j cypher-shell -u neo4j -p graphrag_password `
  "MATCH (n) RETURN labels(n) AS labels, count(n) AS c ORDER BY c DESC"
curl.exe -s http://localhost:6333/collections/grant_chunks

# Live query proof (bob, sre)
# PowerShell: single quotes keep the JSON double quotes literal.
curl.exe -s -X POST http://127.0.0.1:8000/api/v1/query `
  -H "Content-Type: application/json" -H "X-Dev-User: bob" `
  --data-binary '{"query":"Why did the cache stampede happen during the incident, and what mitigation was proposed?","scope":"sre"}'

# ACL leak proof (bob, graph route)
curl.exe -s -X POST http://127.0.0.1:8000/api/v1/query `
  -H "Content-Type: application/json" -H "X-Dev-User: bob" `
  --data-binary '{"query":"Who leads the engineering team that owns the database where the outbox writes?","scope":"sre"}'

# Unauthenticated retrieval leak
curl.exe -s "http://127.0.0.1:8000/api/v1/retrieval/compare?query=Transactional%20Outbox%20postgres%20failure&k=60"

# Golden-set integrity
# (script prints 20 questions / 10 distinct chunk ids / 10 missing)

# Tooling baseline
uv run --directory backend pytest
uv run --directory backend ruff check app tests
uv run --directory backend ruff format --check app tests
uv run --directory backend mypy app tests
cd frontend; npm run lint; npm test; npm run build
```

## Appendix B — Known evidence artifacts (outside repo)

Live outputs were saved under `C:\Users\mahil\AppData\Local\Temp\opencode\`:

- `q1.json` / `q1.out.json` — alice, public scope
- `q2.json` / `q2.out.json` — bob, default scope
- `q3.json` / `q3.out.json` — bob, `sre`
- `q4.json` / `q4.out.json` — bob, graph leak
- `pytest.log`, `api_probe.ps1`, `postingest.py`, `spans2.py`, `schema_counts.py`, `golden_check.py`, `graph_leak.py`, `acl_scope_probe.py`, `retrieval_probe.py`
