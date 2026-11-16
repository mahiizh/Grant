---
title: PolicyEngine Service Specification
doc_id: doc_service_policyengine
acl_scope: security
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# PolicyEngine Service Specification

PolicyEngine is a Tier 2 production service in the GraphRAG lab.

## Overview
PolicyEngine is owned by the Security team. The service owner is Liam Foster.

## SLA
PolicyEngine targets a p99 latency of 100ms and an error budget of 0.4% per 30 days.

## Dependencies
PolicyEngine depends on VectorIndexer for its upstream data path.

## Runbook
Runbook RB-0505 covers PolicyEngine.

## Change Log
Version v1 of PolicyEngine was deployed on 2026-05-07.
