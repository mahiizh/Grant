---
title: OutboxWorker Service Specification
doc_id: doc_service_outboxworker
acl_scope: data-platform
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# OutboxWorker Service Specification

OutboxWorker is a Tier 2 production service in the GraphRAG lab.

## Overview
OutboxWorker is owned by the Data Platform team. The service owner is Priya Nair.

## SLA
OutboxWorker targets a p99 latency of 27ms and an error budget of 0.2% per 30 days.

## Dependencies
OutboxWorker depends on SettlementEngine for its upstream data path.

## Runbook
Runbook RB-0102 covers OutboxWorker.

## Change Log
Version v1 of OutboxWorker was deployed on 2026-02-03.
