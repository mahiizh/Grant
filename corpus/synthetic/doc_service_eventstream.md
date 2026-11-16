---
title: EventStream Service Specification
doc_id: doc_service_eventstream
acl_scope: data-platform
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# EventStream Service Specification

EventStream is a Tier 1 production service in the GraphRAG lab.

## Overview
EventStream is owned by the Data Platform team. The service owner is Alice Chen.

## SLA
EventStream targets a p99 latency of 20ms and an error budget of 0.1% per 30 days.

## Dependencies
EventStream depends on FraudScorer for its upstream data path.

## Runbook
Runbook RB-0101 covers EventStream.

## Change Log
Version v2 of EventStream was deployed on 2026-01-03.
