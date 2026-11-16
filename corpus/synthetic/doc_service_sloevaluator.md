---
title: SloEvaluator Service Specification
doc_id: doc_service_sloevaluator
acl_scope: sre
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# SloEvaluator Service Specification

SloEvaluator is a Tier 1 production service in the GraphRAG lab.

## Overview
SloEvaluator is owned by the Site Reliability Engineering team. The service owner is Bob Kumar.

## SLA
SloEvaluator targets a p99 latency of 80ms and an error budget of 0.2% per 30 days.

## Dependencies
SloEvaluator depends on PolicyEngine for its upstream data path.

## Runbook
Runbook RB-0404 covers SloEvaluator.

## Change Log
Version v1 of SloEvaluator was deployed on 2026-04-06.
