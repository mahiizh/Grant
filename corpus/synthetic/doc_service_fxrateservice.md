---
title: FxRateService Service Specification
doc_id: doc_service_fxrateservice
acl_scope: core-banking
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# FxRateService Service Specification

FxRateService is a Tier 2 production service in the GraphRAG lab.

## Overview
FxRateService is owned by the Core Banking team. The service owner is Nadia Okafor.

## SLA
FxRateService targets a p99 latency of 74ms and an error budget of 0.2% per 30 days.

## Dependencies
FxRateService depends on ChaosRunner for its upstream data path.

## Runbook
Runbook RB-0305 covers FxRateService.

## Change Log
Version v1 of FxRateService was deployed on 2026-05-05.
