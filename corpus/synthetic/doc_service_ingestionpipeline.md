---
title: IngestionPipeline Service Specification
doc_id: doc_service_ingestionpipeline
acl_scope: data-platform
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# IngestionPipeline Service Specification

IngestionPipeline is a Tier 1 production service in the GraphRAG lab.

## Overview
IngestionPipeline is owned by the Data Platform team. The service owner is Alice Chen.

## SLA
IngestionPipeline targets a p99 latency of 41ms and an error budget of 0.4% per 30 days.

## Dependencies
IngestionPipeline depends on RefundService for its upstream data path.

## Runbook
Runbook RB-0104 covers IngestionPipeline.

## Change Log
Version v1 of IngestionPipeline was deployed on 2026-04-03.
