---
title: Dual-Write Consistency and Outbox Ingestion Pattern
doc_id: doc_dual_write_consistency
acl_scope: data-platform
valid_from: 2026-01-10T00:00:00Z
source_tier: 1
---

# Dual-Write Consistency and Outbox Ingestion Pattern

**Author**: Alice Chen  
**Scope**: Data Platform  

## 1. Problem Statement
When applications write directly to both a primary relational database and secondary indices (such as Qdrant vector store or Neo4j knowledge graph), network partitions or unhandled application crashes inevitably create data drift and ghost entities.

## 2. Guaranteed Delivery via Transactional Outbox
To guarantee atomicity and eventual consistency, the system applies the transactional outbox pattern:
1. Ingestion requests insert the canonical document and its decomposed text chunks into PostgreSQL.
2. In the exact same database transaction, rows are inserted into `outbox_events` representing `CHUNK_UPSERTED` or `DOCUMENT_INGESTED`.
3. An asynchronous OutboxWorker polls `outbox_events` and syncs downstream vector embeddings to Qdrant and entity graphs to Neo4j.
4. On success, the event is marked `PROCESSED`. On repeated failure, it transitions to `DEAD_LETTER`.
