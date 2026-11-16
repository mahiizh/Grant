---
title: EmbeddingService Service Specification
doc_id: doc_service_embeddingservice
acl_scope: data-platform
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# EmbeddingService Service Specification

EmbeddingService is a Tier 2 production service in the GraphRAG lab.

## Overview
EmbeddingService is owned by the Data Platform team. The service owner is Tomas Vidal.

## SLA
EmbeddingService targets a p99 latency of 55ms and an error budget of 0.1% per 30 days.

## Dependencies
EmbeddingService depends on LedgerCore for its upstream data path.

## Runbook
Runbook RB-0106 covers EmbeddingService.

## Change Log
Version v2 of EmbeddingService was deployed on 2026-06-03.
