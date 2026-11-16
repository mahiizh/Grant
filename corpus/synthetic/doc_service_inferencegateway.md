---
title: InferenceGateway Service Specification
doc_id: doc_service_inferencegateway
acl_scope: ml-platform
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# InferenceGateway Service Specification

InferenceGateway is a Tier 1 production service in the GraphRAG lab.

## Overview
InferenceGateway is owned by the ML Platform team. The service owner is Noah Kim.

## SLA
InferenceGateway targets a p99 latency of 106ms and an error budget of 0.4% per 30 days.

## Dependencies
InferenceGateway depends on ChatGateway for its upstream data path.

## Runbook
Runbook RB-0604 covers InferenceGateway.

## Change Log
Version v1 of InferenceGateway was deployed on 2026-04-08.
