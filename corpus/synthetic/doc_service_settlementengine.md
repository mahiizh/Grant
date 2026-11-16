---
title: SettlementEngine Service Specification
doc_id: doc_service_settlementengine
acl_scope: payments
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# SettlementEngine Service Specification

SettlementEngine is a Tier 2 production service in the GraphRAG lab.

## Overview
SettlementEngine is owned by the Payments team. The service owner is Sofia Lind.

## SLA
SettlementEngine targets a p99 latency of 47ms and an error budget of 0.4% per 30 days.

## Dependencies
SettlementEngine depends on StatementGenerator for its upstream data path.

## Runbook
Runbook RB-0203 covers SettlementEngine.

## Change Log
Version v1 of SettlementEngine was deployed on 2026-03-04.
