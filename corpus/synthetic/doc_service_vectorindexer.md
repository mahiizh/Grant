---
title: VectorIndexer Service Specification
doc_id: doc_service_vectorindexer
acl_scope: ml-platform
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# VectorIndexer Service Specification

VectorIndexer is a Tier 2 production service in the GraphRAG lab.

## Overview
VectorIndexer is owned by the ML Platform team. The service owner is Pablo Reyes.

## SLA
VectorIndexer targets a p99 latency of 120ms and an error budget of 0.1% per 30 days.

## Dependencies
VectorIndexer depends on CashForecast for its upstream data path.

## Runbook
Runbook RB-0606 covers VectorIndexer.

## Change Log
Version v2 of VectorIndexer was deployed on 2026-06-08.
