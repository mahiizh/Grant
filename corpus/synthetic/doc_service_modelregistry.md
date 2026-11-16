---
title: ModelRegistry Service Specification
doc_id: doc_service_modelregistry
acl_scope: ml-platform
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# ModelRegistry Service Specification

ModelRegistry is a Tier 2 production service in the GraphRAG lab.

## Overview
ModelRegistry is owned by the ML Platform team. The service owner is Iris Novak.

## SLA
ModelRegistry targets a p99 latency of 92ms and an error budget of 0.2% per 30 days.

## Dependencies
ModelRegistry depends on SentimentAnalyzer for its upstream data path.

## Runbook
Runbook RB-0602 covers ModelRegistry.

## Change Log
Version v1 of ModelRegistry was deployed on 2026-02-08.
