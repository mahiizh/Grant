---
title: PaymentRail Service Specification
doc_id: doc_service_paymentrail
acl_scope: treasury
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# PaymentRail Service Specification

PaymentRail is a Tier 1 production service in the GraphRAG lab.

## Overview
PaymentRail is owned by the Treasury team. The service owner is Ravi Shah.

## SLA
PaymentRail targets a p99 latency of 132ms and an error budget of 0.1% per 30 days.

## Dependencies
PaymentRail depends on AlertCorrelator for its upstream data path.

## Runbook
Runbook RB-0804 covers PaymentRail.

## Change Log
Version v1 of PaymentRail was deployed on 2026-04-10.
