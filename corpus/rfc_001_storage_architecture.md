# RFC 001: Hybrid Storage & Ingestion Architecture

**Document ID**: `doc_rfc_storage_001`  
**Author**: Data Platform Team (Lead: Alice Chen)  
**Status**: Accepted  
**Last Updated**: 2026-03-15  

## 1. Overview
The intelligence platform utilizes a hybrid polyglot persistence architecture. To balance transactional integrity with high-dimensional search and relational reasoning, four dedicated storage engines are deployed:
- **PostgreSQL 16**: Acts as the single source of truth for all ingested documents, chunk records, version metadata, and Access Control Lists (ACLs). Writes are staged via an transactional outbox pattern.
- **Qdrant**: Acts as the high-performance vector search engine. It indexes dense semantic embeddings (using 768-dimensional vectors) alongside sparse BM25 vectors for keyword retrieval.
- **Neo4j 5**: Houses the bi-temporal knowledge graph, maintaining entities, relationships, and validity timestamps (`valid_from`, `valid_to`).
- **Redis 7**: Provides in-memory semantic caching using RedisVL to store previous query embeddings and pre-computed answers.

## 2. Ingestion Outbox Mechanism
Direct dual-writing from application workers to both Qdrant and Neo4j is strictly prohibited to prevent split-brain state. All document mutations write an outbox event into PostgreSQL within the same database transaction. The background outbox worker polls events and idempotently syncs downstream stores. A nightly reconciler runs at 02:00 UTC to detect and repair discrepancies between PostgreSQL and the search indices.
