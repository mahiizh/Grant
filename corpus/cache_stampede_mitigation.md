---
title: Runbook: Cache Stampede Mitigation and Probabilistic Early Expiration
doc_id: doc_cache_stampede_mitigation
acl_scope: sre
valid_from: 2026-02-10T00:00:00Z
source_tier: 2
---

# Runbook: Cache Stampede Mitigation and Probabilistic Early Expiration

**Custodian**: Bob Kumar (SRE)  
**Target Component**: Redis Cache Layer  

## 1. Context
When heavily accessed keys expire simultaneously in Redis, hundreds of concurrent RAG queries flood the model gateway and retrieval backends simultaneously, causing gateway latency spikes.

## 2. Mitigation Strategy (XFetch)
We implement optimal probabilistic early expiration:
- Calculate delta = -beta * ln(rand()) * compute_time
- If now - delta >= expiry, asynchronously recompute the response prior to hard expiration.
- Set jitter on TTL values (default: 300s +/- 15%).
