# Item 6b Phase A — preregistered live retrieval baseline

This plan was prepared at commit `0bb7134` and committed in its own commit
before any live retrieval run. It freezes the split, metric, claims, decision
rules, and Phase C row-count rule.
No golden rows are added in Phase A, no gate threshold is changed, and router
patterns are not changed.

## Frozen data

The live comparison uses `split=test` only. The split is frozen by these SHA256
hashes of the committed golden files:

| file | SHA256 |
| --- | --- |
| `evals/golden/questions.jsonl` | `5b3f0e68488cf213ae3202ff3a18a43805057e0f448f7ea98e83f5f085267f97` |
| `evals/golden/multi_turn.jsonl` | `d91447edc8532a6c0cb8ff95759cd23bc75cd15f9297a2a7533d672c8cf5c06b` |
| `evals/golden/generated_questions.jsonl` | `0705342d9f1c5a7df1a4088357cf980df2aad737585f81d9b65bb5a0e9de46e7` |

Frozen test split: 135 rows; sorted test question-id list SHA256
`095a64c2862b7915759d2f1e02a37d06fbc12abe97e7c7722bddf1f424ac6a0e`.
Per-category test rows: `fact` 23, `multi_hop` 22, `global` 21,
`unanswerable` 22, `paraphrase` 22, `multi_turn` 25.

## Configurations

Five configurations run against the same rows, ACL scope, corpus, and retrieval
stack:

- `dense` — dense vector retrieval only.
- `sparse` — BM25 retrieval only.
- `hybrid` — dense + sparse RRF, no reranker.
- `full` — router-directed graph branch feeding the same hybrid RRF + CrossEncoder pool.
- `graph_forced` — always enters the graph branch, bypassing the router, then uses
  the same hybrid RRF + CrossEncoder pool as `full`.

`dense`, `sparse`, `hybrid`, and `full` definitions are unchanged. `graph_forced`
is the "graph" config in the three claims below.

## Live-run controls

- `CONCURRENCY=1` for every configuration.
- Exact/semantic caches disabled; a fresh cold LLM cache per configuration.
- Judge off; no answer-generation model calls. Multi-turn query rewrites are the
  only permitted model calls.
- Isolated eval stores (`graphrag_lab_eval`, `grant_chunks_eval`) so the live
  project stores are not modified.
- `eval_compare --split test --concurrency 1 --retrieval-only --json-dir ...`.

## Primary metric and comparisons

The primary metric is `chunk_ndcg@10`, reported as a paired difference
`(configuration - dense)` over the same question ids. `chunk_recall@5` is a
secondary retrieval metric. Every paired table reports both the row-level
bootstrap 95% percentile CI and the cluster-paired bootstrap 95% percentile CI,
plus the observed paired SD and the cluster-bootstrap SD. Cluster IDs are the
committed golden `cluster_id` values: generated template families and
hand-written source `doc_id`s.

Confirmatory intervals are the **cluster-paired** CIs; row-level CIs are
reported for transparency. Bootstrap iterations use the module defaults and
fixed seeds, so the analysis is reproducible.

## Preregistered claims and decision rules

1. **Overall superiority:** `hybrid > dense` on `chunk_ndcg@10` across all test
   rows iff the cluster-paired 95% CI for the paired difference excludes 0 on
   the positive side.
2. **Multi-hop superiority:** `graph > dense` on `chunk_ndcg@10` within
   `category=multi_hop` iff the cluster-paired 95% CI excludes 0 on the positive
   side.
3. **Fact non-inferiority:** `graph` is not worse than `dense` on
   `chunk_ndcg@10` within `category=fact` iff the cluster-paired 95% CI lower
   bound is greater than `-0.03`.

δ is fixed at **0.05 nDCG**. A claim that fails its rule is recorded as
unresolved; it is not re-tested against a different metric, subset, or CI after
the run. If `full` routes fewer than 50% of `multi_hop` rows to graph, that is
reported as a router finding only and does not trigger a router edit in Phase A.

## Phase C row-count rule (written before results)

For each unresolved claim:

- `n_needed = ceil((2.8 × SD / δ)²)`, where `SD` is the cluster-bootstrap SD of
  the paired `chunk_ndcg@10` differences for that category and δ = 0.05.
- `clusters_needed = ceil(n_needed / (rows_held / clusters_held))` for that
  category, with at least one row per cluster when a category has no clusters.
- `gap = n_needed - rows_held` (floored at 0). Categories are ranked by
  **descending gap**, never by absolute score, and rows are added only to the
  ranked categories in Phase C after approval.
- Gate thresholds stay total ≥150, test ≥120, and ≥20 per test category.

## Reporting

The Phase A report in `STATUS.md` §0.8 includes the five-config table, paired
difference table with both CIs and SDs, router counts for `multi_hop`, retrieval
p50/p95, and the per-category `n_needed` table. Work stops there for approval;
no golden rows are added and no thresholds are tuned.
