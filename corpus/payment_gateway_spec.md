---
title: Payment Gateway Architecture and Routing Specification
doc_id: doc_payment_gateway_spec
acl_scope: payments
valid_from: 2026-02-15T00:00:00Z
source_tier: 1
---

# Payment Gateway Architecture and Routing Specification

**Owner**: Elena Rostova (Payments Team)  
**Classification**: Internal Payments  

## 1. System Overview
`PaymentGateway` orchestrates authorization, capture, and settlement across tier-1 card acquirers (Stripe, Adyen, and ChasePay). It implements dynamic provider fallback based on rolling 60-second success rates.

## 2. Idempotency & Reconciliations
Every charge request requires a unique client-generated `Idempotency-Key` passed via HTTP headers. Keys are persisted in Redis with an 86400-second TTL. If a duplicate key arrives within 24 hours, the cached HTTP response is returned verbatim without re-invoking downstream processors.
