---
title: RFC-004 Bitemporal Knowledge Graph Indexing
doc_id: doc_rfc_004
acl_scope: data-platform
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# RFC-004 Bitemporal Knowledge Graph Indexing

**Author**: Alice Chen  
**Status**: Accepted  

## 1. Temporal Dimensions
The knowledge graph maintains two orthogonal temporal axes:
- **Valid Time (`valid_from`, `valid_to`)**: The period during which a real-world fact or contract holds true in the business domain.
- **Transaction Time (`ingested_at`)**: The timestamp when the fact was written to the PostgreSQL database.

## 2. Point-in-Time Traversal
Every Cypher query executing over Neo4j and every Qdrant vector filter must respect the `as_of` timestamp supplied in the retrieval context.
Relationships and nodes where `valid_from > as_of` or `valid_to <= as_of` must be pruned from candidate expansion paths.
