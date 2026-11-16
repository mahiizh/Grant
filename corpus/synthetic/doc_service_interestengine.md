---
title: InterestEngine Service Specification
doc_id: doc_service_interestengine
acl_scope: core-banking
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# InterestEngine Service Specification

InterestEngine is a Tier 2 production service in the GraphRAG lab.

## Overview
InterestEngine is owned by the Core Banking team. The service owner is Kenji Sato.

## SLA
InterestEngine targets a p99 latency of 60ms and an error budget of 0.5% per 30 days.

## Dependencies
InterestEngine depends on SloEvaluator for its upstream data path.

## Runbook
Runbook RB-0303 covers InterestEngine.

## Change Log
Version v1 of InterestEngine was deployed on 2026-03-05.
