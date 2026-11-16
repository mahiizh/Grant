---
title: CapacityPlanner Service Specification
doc_id: doc_service_capacityplanner
acl_scope: sre
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# CapacityPlanner Service Specification

CapacityPlanner is a Tier 2 production service in the GraphRAG lab.

## Overview
CapacityPlanner is owned by the Site Reliability Engineering team. The service owner is Omar Haddad.

## SLA
CapacityPlanner targets a p99 latency of 73ms and an error budget of 0.1% per 30 days.

## Dependencies
CapacityPlanner depends on ThreatScanner for its upstream data path.

## Runbook
Runbook RB-0403 covers CapacityPlanner.

## Change Log
Version v1 of CapacityPlanner was deployed on 2026-03-06.
