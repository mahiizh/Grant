---
title: RefundService Service Specification
doc_id: doc_service_refundservice
acl_scope: payments
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# RefundService Service Specification

RefundService is a Tier 2 production service in the GraphRAG lab.

## Overview
RefundService is owned by the Payments team. The service owner is Marcus Webb.

## SLA
RefundService targets a p99 latency of 61ms and an error budget of 0.1% per 30 days.

## Dependencies
RefundService depends on ReconciliationJob for its upstream data path.

## Runbook
Runbook RB-0205 covers RefundService.

## Change Log
Version v1 of RefundService was deployed on 2026-05-04.
