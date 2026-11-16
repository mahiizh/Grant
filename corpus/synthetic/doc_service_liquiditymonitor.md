---
title: LiquidityMonitor Service Specification
doc_id: doc_service_liquiditymonitor
acl_scope: treasury
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# LiquidityMonitor Service Specification

LiquidityMonitor is a Tier 2 production service in the GraphRAG lab.

## Overview
LiquidityMonitor is owned by the Treasury team. The service owner is Clara Moreau.

## SLA
LiquidityMonitor targets a p99 latency of 118ms and an error budget of 0.4% per 30 days.

## Dependencies
LiquidityMonitor depends on LimitEngine for its upstream data path.

## Runbook
Runbook RB-0802 covers LiquidityMonitor.

## Change Log
Version v1 of LiquidityMonitor was deployed on 2026-02-10.
