# Synthetic Corpus for the Lab

This directory contains the synthetic corpus used for testing the GraphRAG Intelligence Lab.
It includes:
- Architectural specifications and RFCs
- Operational runbooks and incident postmortems
- Service definitions and team directories
- Versioned SLA agreements (v1 vs v2 with temporal changes)
- Sensitive executive audit reports (restricted to `executive-audit` scope)
- Adversarial prompt-injection evaluation benchmarks (`corpus/adversarial/`)

## Generated corpus (`corpus/synthetic/`)

The hand-authored documents alone are too small to distinguish retrieval
configurations: with 15 documents, dense, sparse, and hybrid all find the same
chunk. `corpus/synthetic/` adds a deterministic generated corpus that keeps the
same schema but introduces the cases retrieval actually has to get right.

| Property | Value |
| --- | --- |
| Generator | `backend/app/tools/generate_eval_assets.py` |
| Seed | `20260412` (all output is byte-for-byte reproducible) |
| Generated documents | 170 |
| Generated chunks | 800 |
| Corpus total | 185 documents / 845 chunks |
| Manifest | `corpus/synthetic/manifest.json` |

Every generated document is Markdown with the same frontmatter as the
hand-authored corpus (`doc_id`, `title`, `acl_scope`, `valid_from`,
`source_tier`), so it flows through the normal ingestion path. Document families:

- **Service specifications** (`doc_service_*`) — owner, team, p99 target, error
  budget, dependency, runbook id, deployed version.
- **Runbooks** (`doc_runbook_*`) — escalation path and p99 threshold; near-duplicate
  wording to the service spec.
- **Incident cards** (`doc_incident_*`) — incident id, impact, and the service
  involved.
- **Team directories** (`doc_team_*`) — lead, members, and the services the team
  owns, which is what makes ownership chains multi-hop.
- **Versioned SLAs** (`doc_sla_*_v1`, `_v2`, `_v1_mirror`) — the same service with
  a superseded target, a current target, and an audit mirror whose p99 differs
  from v1 by 1 ms. The mirror exists so a lexical retriever that grabs the first
  "v1" match is visibly wrong rather than accidentally right.

Access control is exercised too: generated documents carry real team slugs
(`security`, `ml-platform`, `customer-support`, `treasury`, `risk`,
`compliance`), not just the legacy `sre` / `payments` scopes.

### Reproducing

```powershell
uv run --directory backend python -m app.tools.generate_eval_assets
uv run --directory backend python -m app.tools.generate_eval_assets --check
```

`--check` re-reads the committed corpus, recomputes the chunk ids, and fails if
the manifest counts or generated golden ids no longer match. CI runs it, so a
hand edit to a generated file cannot drift silently.
