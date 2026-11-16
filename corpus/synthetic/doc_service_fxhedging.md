---
title: FxHedging Service Specification
doc_id: doc_service_fxhedging
acl_scope: treasury
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# FxHedging Service Specification

FxHedging is a Tier 2 production service in the GraphRAG lab.

## Overview
FxHedging is owned by the Treasury team. The service owner is Jonas Berg.

## SLA
FxHedging targets a p99 latency of 125ms and an error budget of 0.5% per 30 days.

## Dependencies
FxHedging depends on StressTester for its upstream data path.

## Runbook
Runbook RB-0803 covers FxHedging.

## Change Log
Version v1 of FxHedging was deployed on 2026-03-10.
