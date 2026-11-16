---
title: SweepEngine Service Specification
doc_id: doc_service_sweepengine
acl_scope: treasury
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# SweepEngine Service Specification

SweepEngine is a Tier 2 production service in the GraphRAG lab.

## Overview
SweepEngine is owned by the Treasury team. The service owner is Jonas Berg.

## SLA
SweepEngine targets a p99 latency of 26ms and an error budget of 0.3% per 30 days.

## Dependencies
SweepEngine depends on RetentionManager for its upstream data path.

## Runbook
Runbook RB-0806 covers SweepEngine.

## Change Log
Version v2 of SweepEngine was deployed on 2026-06-10.
