---
title: Service Level Agreement: Payments API v1
doc_id: doc_sla_payments_v1
acl_scope: payments
valid_from: 2026-01-01T00:00:00Z
valid_to: 2026-03-15T00:00:00Z
source_tier: 1
---

# Service Level Agreement: Payments API v1

**Owner**: Elena Rostova  
**Effective Period**: 2026-01-01 to 2026-03-15  

## 1. Availability Objective
The Payments API commits to a monthly uptime of 99.95%, excluding scheduled maintenance windows notified 72 hours in advance.

## 2. Latency Thresholds
- **Median (p50) Latency**: Maximum 20ms for authorization requests under peak load (5,000 TPS).
- **Tail (p99) Latency**: The p99 latency SLA for payment authorization is strictly 50ms. Any degradation above 50ms triggers Sev-2 alerting.

## 3. Financial Remedies
If availability drops below 99.9% in any calendar month, a 15% billing credit is applied to merchant invoices.
