# Revamp final verification

Date: 2026-11-27
Branch: `revamp`
Code verified: Ask SSE token streaming plus deferred cache-hit history on `revamp`
(parent HEAD `40b2fa2`; this document is part of that single isolated commit).

## Isolation and scope

Only the isolated test stores were used:

- PostgreSQL: `graphrag_lab_test`
- Qdrant: `grant_chunks_test`, `grant_entities_test`
- Neo4j: `bolt://localhost:7688`
- Redis: DB `1`

Dev stores were not read or written. The intentionally uncommitted user work
(`Makefile`, `README.md`, `frontend/package.json`, `frontend/package-lock.json`,
`backups/`) was excluded from all commits. Nothing was pushed or merged.

## Test results

- Full isolated backend suite: **184 passed, 2 warnings in 112.64 s**
  (`full_suite_after_cache_defer.log`; the 2 warnings are pre-existing dependency warnings).
- Targeted streaming and deferred-history subset: **17 passed in 6.21 s**
  (`cache_defer_targeted2.log`).
- Frontend: `npm run lint` (`tsc --noEmit`) passed; `npm test -- --run` passed
  **13 tests across 3 files** (`frontend_tests_final_after_cache_defer.log`).
  There is no separate `typecheck` script; the canvas warnings in the test log are harmless.

## Streaming implementation

- `POST /api/v1/query/stream` and `POST /threads/{thread_id}/messages?stream=true`
  emit SSE events `token`, `stage`, `citations`, `done`, and `error`.
- `ModelGateway.stream_complete(..., on_token=...)` forwards real LiteLLM deltas;
  cached, mock, and fake paths emit token-sized pieces. The orchestrator uses a
  `token_sink`, and the `done` event includes `ttft_ms`.
- The Ask UI appends tokens live and renders `source`, `path`, and `top_score`;
  SSE `error` events are surfaced rather than silently dropped.
- Cache-hit `QueryHistory` persistence is deferred with `asyncio.create_task` via
  `defer_cache_history=True`. History is still recorded; it is no longer on the
  cache-hit response path.

## Rerank and answer metadata

Rerank was ON during all live validation: `RERANK_ENABLED=True`,
`RERANK_MAX_CANDIDATES=10`, `RERANK_MAX_LENGTH=256`, `RERANK_TARGET_MS=800.0`.
In the 20-question docs run, rerank was p50 **26.835 ms**, p95 **38.67 ms**, max
**100.71 ms**, so no fallback to `RERANK_ENABLED=false` was needed.

Every answer path stores `source`, `path`, `top_score`, and `stage_timings_ms`.

## Clean 20-question docs Ask rerun

Artifact: `isomd20_final_current.json`.

- Latency: n=20, min **725.345 ms**, p50 **1052.392 ms**, p95 **2031.67 ms**,
  max **2062.63 ms**, mean **1219.608 ms**.
- LLM stage: n=20, min **605.37 ms**, p50 **907.805 ms**, p95 **1870.44 ms**,
  max **1939.83 ms**, mean **1071.167 ms**.
- LLM distribution: `<1s` 11, `1-2s` 9, `2-3s` 0, `3-5s` 0, `5-10s` 0, `>=10s` 0.
- All 20 answers were `docs`, all were cache misses, all were grounded, and none
  used the web.

## Fresh web probes

Artifact: `web3_fresh_current.json`. All three forced-web probes were fresh cache
misses, resolved as `source_kind=web`, and used web evidence from graspreach.

| Query | Latency | Web stage |
| --- | --- | --- |
| Ulaanbaatar population 2026 | 3963.945 ms | 2461.85 ms |
| 2026 FIFA World Cup final | 4297.221 ms | 3395.2 ms |
| Tungsten atomic number | 3740.326 ms | 3005.58 ms |

Observed domains included `worldpopulationreview.com`, `fifa.com`, `apnews.com`,
`bbc.com`, `pdg.lbl.gov`, `rsc.org`, and `pubchem.ncbi.nlm.nih.gov`. The
`graspreach in-process search failed; using subprocess` log line is harmless: the
subprocess path succeeded for all three probes.

## SSE TTFT

Artifact: `ttft_streaming_final3.json` (final rerun on the same build after the
clean baseline).

- Docs: n=3, p50 **2203.88 ms**, p95 **5574.88 ms**.
- Web: n=3, p50 **5227.58 ms**, p95 **6992.34 ms**.
- Thread stream sample: **4060.29 ms**.
- All streams matched their accumulated answer, had no `error` events, and used
  cache misses with the expected docs/web source classifications.

An earlier run on the same code (`ttft_streaming_final.json`) measured docs p50
**1852.09 ms** / p95 **2021.77 ms**, web p50 **3576.21 ms** / p95 **5126.98 ms**,
and thread **1429.4 ms**. No TTFT SLA was specified; the spread is dominated by
provider LLM latency, not retrieval, rerank, or persistence.

## Final live baseline (`baseline_final_deferred_history3`)

Clean isolated stores and Redis DB 1 were reset immediately before the run.
Raw artifact: `C:\Users\mahil\AppData\Local\Temp\opencode\baseline_final_deferred_history3.json`.
Memory peaks came from `memory_final_baseline3.json` over the same live window.

| Target | Measured | Result |
| --- | --- | --- |
| upload < 1 s | 31.749 ms (202, job completed) | PASS |
| health during ingest < 100 ms | n=218, p50 3.968 ms / p95 8.558 ms / max 24.265 ms | PASS |
| cache hit < 50 ms | 5/5 hits, p50 13.651 ms / p95 19.913 ms / max 19.913 ms | PASS |
| docs Ask p95 < 4 s | p50 1947.859 ms / p95 2045.642 ms | PASS |
| web Ask p95 < 15 s | p50 2672.92 ms / p95 3372.156 ms | PASS |
| API < 1.5 GB | peak working set 1087.6 MB | PASS |
| worker < 3 GB | peak working set 1777.9 MB | PASS |

The post-upload invalidation ask was **1998.91 ms** with `is_cached=false`,
confirming the owner `index_version` bump. An intermediate run
(`baseline_final_deferred_history2`) had docs p95 **8159.802 ms** because one
provider LLM call took **7726.33 ms**; the stores were reset and the baseline was
rerun to produce the clean result above. No code change was made to compensate
for provider variance.
