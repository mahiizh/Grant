---
title: BalanceAggregator Service Specification
doc_id: doc_service_balanceaggregator
acl_scope: treasury
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# BalanceAggregator Service Specification

BalanceAggregator is a Tier 2 production service in the GraphRAG lab.

## Overview
BalanceAggregator is owned by the Treasury team. The service owner is Clara Moreau.

## SLA
BalanceAggregator targets a p99 latency of 139ms and an error budget of 0.2% per 30 days.

## Dependencies
BalanceAggregator depends on ModelValidator for its upstream data path.

## Runbook
Runbook RB-0805 covers BalanceAggregator.

## Change Log
Version v1 of BalanceAggregator was deployed on 2026-05-10.
