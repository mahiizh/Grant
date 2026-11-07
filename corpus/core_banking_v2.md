---
title: Core Banking System v2 Architecture and Ledger Model
doc_id: doc_core_banking_v2
acl_scope: core-banking
valid_from: 2026-03-01T00:00:00Z
source_tier: 1
---

# Core Banking System v2 Architecture and Ledger Model

**Architect**: Dave Miller (Core Banking Team)  
**System**: `CoreBanking`  

## 1. Double-Entry General Ledger
`CoreBanking` v2 enforces an immutable double-entry bookkeeping ledger on PostgreSQL 16. Every financial transaction consists of at least two journal entries balancing debits and credits:
- Sum(Debits) == Sum(Credits)
- Ledger entries are append-only; balance adjustments require offsetting compensating transactions.

## 2. Multi-Currency Settlement
Foreign exchange rates are updated hourly from the central treasury feed. The exchange rate service publishes updates to the Redis cache cluster with key `fx:rate:<currency_pair>`.
