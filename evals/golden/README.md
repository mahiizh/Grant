# Golden evaluation data

This directory holds the human-authored golden sets used by `make eval` and the
CI evaluation gate. Every row is grounded in the synthetic corpus under
`corpus/`, and every `expected_chunk_ids` entry is a real chunk id produced by
`parse_markdown` + `chunk_parsed_document` over that corpus.

## Files

| File | Rows | Purpose |
| --- | --- | --- |
| `questions.jsonl` | 20 | Single-turn questions across `fact`, `multi_hop`, `global`, `unanswerable`, `paraphrase` |
| `multi_turn.jsonl` | 10 | Follow-up questions that require pronoun/context resolution |

## Dev / test split

Each row carries a `split` field:

- `dev` — tuning only. Use it while changing retrieval, prompts, or routing.
- `test` — gate only. `make eval` and CI score this split; never tune on it.

| File | dev | test |
| --- | --- | --- |
| `questions.jsonl` | 10 | 10 |
| `multi_turn.jsonl` | 5 | 5 |

The split is a property of the row, not of the file, so a row can be moved
between splits without changing the file layout.

## Provenance and chunk ids

Chunk ids have the form `chk_{doc_id}_{index:04d}_{sha256(text)[:10]}`. They are
deterministic for a given corpus text, so the same ids are produced by the live
ingestion pipeline and by the Docker-free hermetic test harness. The CI gate
asserts that every golden `expected_chunk_ids` entry exists after ingestion; a
missing id fails the run instead of silently scoring against a fake id.

The corpus contains 15 documents and 45 chunks (12 top-level documents plus 3
adversarial documents under `corpus/adversarial/`).

## Dependencies

Paraphrase rows set `depends_on` to the parent question they paraphrase. The
runner executes the parent first in the same orchestrator so the answer is
cached naturally; it never pre-seeds the cache. The paraphrase then measures
whether the cache returns the parent answer.

## Non-goals

- No threshold tuning. Item 2 only builds the honest measurement machinery; the
  real baseline is recorded separately.
- No fabricated ids. If a question cannot be grounded in a real chunk, it does
  not belong here.
