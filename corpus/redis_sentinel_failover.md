---
title: Runbook: Redis Sentinel Failover and Topology Verification
doc_id: doc_redis_sentinel_failover
acl_scope: sre
valid_from: 2026-03-20T00:00:00Z
source_tier: 2
---

# Runbook: Redis Sentinel Failover and Topology Verification

**Custodian**: Bob Kumar (SRE)  
**Cluster**: Production Redis Sentinel  

## 1. Failure Detection
Sentinel nodes ping the primary master every 1,000ms. If the master fails to respond for `down-after-milliseconds 5000`, a subjective down (`sdown`) state is registered. When a quorum of 2 sentinels agree, the state transitions to objective down (`odown`).

## 2. Manual Promotion Procedure
In case of split-brain or network isolation:
1. Verify replica lag: `redis-cli -p 6380 info replication`
2. Elect the replica with lowest `master_repl_offset`.
3. Issue promotion command: `SENTINEL failover mymaster`
4. Verify application connection pool handles reconnection within 250ms.
