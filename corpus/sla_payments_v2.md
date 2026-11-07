---
title: Service Level Agreement: Payments API v2
doc_id: doc_sla_payments_v2
acl_scope: payments
valid_from: 2026-03-15T00:00:00Z
source_tier: 1
---

# Service Level Agreement: Payments API v2

**Owner**: Elena Rostova  
**Effective Period**: 2026-03-15 onwards  

## 1. Availability Objective
The Payments API commits to an elevated monthly uptime of 99.99%, backed by multi-region active-active deployment.

## 2. Latency Thresholds
- **Median (p50) Latency**: Maximum 10ms for authorization requests under peak load (10,000 TPS).
- **Tail (p99) Latency**: The p99 latency SLA for payment authorization is strictly 25ms. Following infrastructure optimizations completed in March 2026, the latency ceiling was lowered from the previous 50ms requirement to 25ms.

## 3. Financial Remedies
If availability drops below 99.95% in any calendar month, a 25% billing credit is applied to merchant invoices.
