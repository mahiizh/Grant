---
title: LimitEngine Service Specification
doc_id: doc_service_limitengine
acl_scope: risk
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# LimitEngine Service Specification

LimitEngine is a Tier 2 production service in the GraphRAG lab.

## Overview
LimitEngine is owned by the Risk team. The service owner is Sana Iqbal.

## SLA
LimitEngine targets a p99 latency of 138ms and an error budget of 0.1% per 30 days.

## Dependencies
LimitEngine depends on RegulatoryReporter for its upstream data path.

## Runbook
Runbook RB-0903 covers LimitEngine.

## Change Log
Version v1 of LimitEngine was deployed on 2026-03-11.
