---
title: FeatureStore Service Specification
doc_id: doc_service_featurestore
acl_scope: ml-platform
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# FeatureStore Service Specification

FeatureStore is a Tier 1 production service in the GraphRAG lab.

## Overview
FeatureStore is owned by the ML Platform team. The service owner is Noah Kim.

## SLA
FeatureStore targets a p99 latency of 85ms and an error budget of 0.1% per 30 days.

## Dependencies
FeatureStore depends on KnowledgeBase for its upstream data path.

## Runbook
Runbook RB-0601 covers FeatureStore.

## Change Log
Version v2 of FeatureStore was deployed on 2026-01-08.
