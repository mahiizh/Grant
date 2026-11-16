---
title: RetentionManager Service Specification
doc_id: doc_service_retentionmanager
acl_scope: compliance
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# RetentionManager Service Specification

RetentionManager is a Tier 1 production service in the GraphRAG lab.

## Overview
RetentionManager is owned by the Compliance team. The service owner is Helena Voss.

## SLA
RetentionManager targets a p99 latency of 137ms and an error budget of 0.5% per 30 days.

## Dependencies
RetentionManager depends on OutboxWorker for its upstream data path.

## Runbook
Runbook RB-1001 covers RetentionManager.

## Change Log
Version v2 of RetentionManager was deployed on 2026-01-12.
