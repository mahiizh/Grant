---
title: Incident Postmortem: INC-2026-04 Payment Degradation
doc_id: doc_postmortem_inc_04
acl_scope: sre
valid_from: 2026-04-12T15:35:00Z
source_tier: 1
---

# Incident Postmortem: INC-2026-04 Payment Degradation

**Incident Commander**: Bob Kumar (SRE Team)  
**Severity**: Sev-1  
**Impacted Service**: `PaymentGateway`  

## 1. Summary
On April 12, 2026, between 14:10 and 15:35 UTC, customers experienced a 24% failure rate when processing credit card transactions through `PaymentGateway`. The root cause was identified as stale cache entries in Redis following an unscheduled deployment by the Core Banking team.

## 2. Root Cause Analysis
During deployment v2.4.1 of `CoreBanking`, the database migration updated the exchange rate table in PostgreSQL. However, the outbox worker encountered a deserialization error on the invalidation event, leaving expired exchange rates in the Redis cache. `PaymentGateway` rejected transactions that failed the currency consistency check.

## 3. Remediation & Action Items
1. Added dead-letter queue (DLQ) monitoring for outbox consumer failures (Assigned to: Data Platform Team / Alice Chen).
2. Implemented mandatory cache invalidation verification checks prior to traffic shifting (Assigned to: Core Banking Team / Dave Miller).
3. Updated automated failover thresholds in the payment proxy (Assigned to: SRE Team / Bob Kumar).
