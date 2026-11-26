# Revamp final verification

Date: 2026-11-26
Branch: `revamp`
Code verified: HEAD `9f8065d` (Step 7 Graph UI)

## Isolation and scope

Only the isolated test stores were used:

- PostgreSQL: `graphrag_lab_test`
- Qdrant: `grant_chunks_test`, `grant_entities_test`
- Neo4j: `bolt://localhost:7688`
- Redis: DB `1`

Dev stores were not read or written. The intentionally uncommitted user work
(`Makefile`, `README.md`, `frontend/package.json`, `frontend/package-lock.json`,
`backups/`) was excluded from all commits. Nothing was pushed.

## Test results

- Full isolated backend suite: **180 passed, 2 warnings in 103.08 s**
  (`step8_full_suite.log`; the 2 warnings are pre-existing dependency warnings).
- Targeted Step 8 regression subset: **11 passed, 28 deselected in 10.24 s**
  (`step8_regressions.log`).
- Frontend from Step 7: `npm run lint` (tsc --noEmit) passed and `npm test`
  passed **11 tests across 2 files**.

## Regression coverage

| Step 8 requirement | Evidence |
| --- | --- |
| upload < 1 s | Live baseline upload **30.958 ms**, status 202, job `completed`. |
| health responsive during ingest | 232 health samples during ingest: p50 **4.188 ms**, p95 **9.417 ms**, max **19.820 ms**. |
| cache miss after new upload (`index_version`) | Baseline post-upload ask **2056.372 ms**, `is_cached=false`. Unit coverage: `test_upload_version_bump_turns_repeat_hit_into_miss`, `test_outbox_cache_invalidation_lifecycle`, `test_version_bump_is_owner_scoped`. |
| repeat web question answered from ingested chunks without a web call | `test_repeat_question_retrieves_indexed_web_chunks`: second answer uses indexed evidence; `retriever.search_calls == [query, query]` and `mock_graspreach.client.gather_calls == [query]`. |
| owner-scope isolation | `test_acl_live` (Qdrant payload, Neo4j Cypher, retrieval compare, graph endpoints), `test_acl_leaks`, `test_web_evidence_write_back_is_owner_scoped`, and the Step 7 graph UI live-store ACL test. |
| `grounded_only` abstains | `test_not_found_routes_to_web_or_abstains_by_policy` grounded-only branch: `is_abstention=True`; also `test_abstain_path_records_all_answer_metadata`. |
| `NOT_FOUND` → web | Same test, `grounded_plus_web` branch: `source_kind=web`, one web gather call. |

## Final live baseline (`baseline_step8_final`)

Clean isolated stores and Redis DB 1 were reset immediately before the run.
Raw artifact: `C:\Users\mahil\AppData\Local\Temp\opencode\baseline_step8_final.json`.

| Target | Measured | Result |
| --- | --- | --- |
| upload < 1 s | 30.958 ms (202, job completed) | PASS |
| health during ingest < 100 ms | p50 4.188 ms / p95 9.417 ms / max 19.820 ms | PASS |
| cache hit < 50 ms | 5/5 hits, p50 26.134 ms / p95 30.509 ms | PASS |
| docs Ask p95 < 4 s | p50 2886.464 ms / p95 11675.764 ms | FAIL |
| web Ask p95 < 15 s | p50 2205.080 ms / p95 2494.453 ms | PASS |
| API < 1.5 GB | peak working set 928.2 MB | PASS |
| worker < 3 GB | peak working set 2524.4 MB | PASS |

The docs Ask p95 miss is entirely provider LLM latency: the three docs-stage
breakdowns were embed 11.69/9.08/5.49 ms, Qdrant 22.04/18.79/18.35 ms,
rerank 26.73/29.80/29.63 ms, LLM 2736.07/1457.63/11531.73 ms, persist
13.41/11.91/14.86 ms. Retrieval, rerank and persistence stayed well below their
budgets; one 11.5 s provider call dominates the p95. No code change was made to
compensate for provider variance.

Forced-web stage breakdown (all resolved as `web`): 4879.942 ms
(web 2872.15, LLM 1927.56), 5426.099 ms (web 2612.00, LLM 2720.68), and
4925.911 ms (web 3754.27, LLM 1077.93). The post-upload invalidation ask was
2056.372 ms with `is_cached=false`, confirming the index-version bump.
