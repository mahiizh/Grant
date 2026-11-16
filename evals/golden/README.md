# Golden evaluation data

This directory holds the golden sets used by `make eval` and the CI evaluation
gate. Every row is grounded in the synthetic corpus under `corpus/`, and every
`expected_chunk_ids` entry is a real chunk id produced by `parse_markdown` +
`chunk_parsed_document` over that corpus.

## Files

| File | Rows | Purpose |
| --- | --- | --- |
| `questions.jsonl` | 20 | Hand-authored single-turn questions across `fact`, `multi_hop`, `global`, `unanswerable`, `paraphrase` |
| `multi_turn.jsonl` | 10 | Hand-authored follow-ups that require pronoun/context resolution |
| `generated_questions.jsonl` | 210 | Generated from `corpus/synthetic/`; same schema, grounded ids |

Total: **240 rows**, **105 dev / 135 test**.

## Dev / test split

Each row carries a `split` field:

- `dev` — tuning only. Use it while changing retrieval, prompts, or routing.
- `test` — gate only. `make eval` and CI score this split; never tune on it.

Test rows per category (the gate requires ≥20 in each):

| category | test rows |
| --- | --- |
| `fact` | 23 |
| `multi_hop` | 22 |
| `global` | 21 |
| `unanswerable` | 22 |
| `paraphrase` | 22 |
| `multi_turn` | 25 |

The split is a property of the row, not of the file, so a row can be moved
between splits without changing the file layout. `make eval` reads the row
counts from `corpus/synthetic/manifest.json` instead of hardcoding them, and
`generate_eval_assets --check` fails if the manifest and the committed rows
disagree.

## Generated rows

`backend/app/tools/generate_eval_assets.py` derives the generated rows from the
generated corpus with a fixed seed, so they are reproducible and reviewable.
They target the failure modes the hand-authored set cannot express at scale:

- `fact` — p99 targets and ownership, including rows whose answer changes
  between SLA v1 and v2.
- `multi_hop` — service → dependency → owning team chains that cross team
  boundaries, so a one-hop retriever retrieves the right service but the wrong
  team.
- `global` — "how many services does team X own" style questions that need the
  team directory plus the service documents.
- `unanswerable` — questions about 30 service names that are deliberately absent
  from the corpus, so a lexical near-match cannot make them answerable.
- `paraphrase` — rewording of a parent fact question; the parent runs first and
  the cache is never pre-seeded.
- `multi_turn` — a parent question followed by "What is its p99 latency SLA?",
  with `expected_rewritten_query` recording the standalone form.

## Provenance and chunk ids

Chunk ids have the form `chk_{doc_id}_{index:04d}_{sha256(text)[:10]}`. They are
deterministic for a given corpus text, so the same ids are produced by the live
ingestion pipeline and by the Docker-free hermetic test harness. The CI gate
asserts that every golden `expected_chunk_ids` entry exists after ingestion; a
missing id fails the run instead of silently scoring against a fake id.

The corpus contains 185 documents and 845 chunks (170 generated documents plus
the hand-authored documents, including the adversarial set under
`corpus/adversarial/`).

## Dependencies

Paraphrase rows set `depends_on` to the parent question they paraphrase. The
runner executes the parent first in the same orchestrator so the answer is
cached naturally; it never pre-seeds the cache. The paraphrase then measures
whether the cache returns the parent answer.

Multi-turn rows carry `thread_turns` instead, and the runner replays those turns
before the follow-up.

## Judge calibration

Answer quality is scored by a DeepEval `GEval` judge routed through
`app.llm.gateway.ModelGateway` (same budget, cache, and retry policy as the
pipeline). The judge is **off by default**; enable it with `make eval JUDGE=1`
or `--judge`.

Calibration uses `evals/calibration/judge_answers.jsonl`: 30 answers with binary
human labels, balanced 15 correct / 15 wrong. The labels were authored by the
implementer from dev-split golden rows, not by an independent annotator, so the
agreement figure is a consistency check, not inter-annotator agreement.
`make calibrate-judge` reruns the judge and writes
`evals/calibration/judge_agreement.json`.

Last committed run (`gemini/gemini-3.5-flash-lite`, threshold 0.5):
**raw agreement 0.9333, Cohen's kappa 0.8667, n=30**. The two disagreements are
both `score=0.1` verdicts whose stated reason says the answer is correct; the
judge's score and its prose are inconsistent on those rows, which is why the
agreement number is reported rather than assumed.

## Non-goals

- No threshold tuning. The measurement machinery is built first; baselines are
  recorded separately.
- No fabricated ids. If a question cannot be grounded in a real chunk, it does
  not belong here.
