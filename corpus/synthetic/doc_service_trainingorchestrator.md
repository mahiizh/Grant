---
title: TrainingOrchestrator Service Specification
doc_id: doc_service_trainingorchestrator
acl_scope: ml-platform
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# TrainingOrchestrator Service Specification

TrainingOrchestrator is a Tier 2 production service in the GraphRAG lab.

## Overview
TrainingOrchestrator is owned by the ML Platform team. The service owner is Pablo Reyes.

## SLA
TrainingOrchestrator targets a p99 latency of 99ms and an error budget of 0.3% per 30 days.

## Dependencies
TrainingOrchestrator depends on EscalationEngine for its upstream data path.

## Runbook
Runbook RB-0603 covers TrainingOrchestrator.

## Change Log
Version v1 of TrainingOrchestrator was deployed on 2026-03-08.
