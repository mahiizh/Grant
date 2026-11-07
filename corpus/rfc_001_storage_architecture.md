---
title: RFC-001 Storage Tiering & Hybrid Indexing Architecture
doc_id: doc_rfc_001
acl_scope: data-platform
valid_from: 2026-01-15T00:00:00Z
source_tier: 1
---

# RFC-001 Storage Tiering & Hybrid Indexing Architecture

**Author**: Alice Chen (Data Platform Team)  
**Status**: Approved  
**Target Systems**: PostgreSQL, Qdrant, Neo4j, Redis  

## 1. Overview
This RFC specifies the storage tiering and hybrid retrieval topology for the GraphRAG Intelligence Lab. PostgreSQL acts as the single source of truth for canonical documents and transactional outbox events.

## 2. Storage Tier Responsibilities
- **PostgreSQL**: Primary transactional store. Stores raw documents, chunk records, and outbox mutation events.
- **Qdrant**: Vector search engine. Stores 384-dimensional dense vectors (BAAI/bge-small-en-v1.5) and BM25 sparse vectors.
- **Neo4j**: Graph store. Indexes entities, relationships, temporal validity intervals, and ACL scopes.
- **Redis**: Low-latency cache. Caches exact prompt-answer pairs and semantic embeddings with entity validation guardrails.

## 3. Consistency Model
Dual-write synchronization is strictly prohibited. All asynchronous mutations must flow through PostgreSQL's transactional outbox table (`outbox_events`) to prevent partial failures and state drift.
