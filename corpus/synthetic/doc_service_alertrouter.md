---
title: AlertRouter Service Specification
doc_id: doc_service_alertrouter
acl_scope: sre
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# AlertRouter Service Specification

AlertRouter is a Tier 1 production service in the GraphRAG lab.

## Overview
AlertRouter is owned by the Site Reliability Engineering team. The service owner is Bob Kumar.

## SLA
AlertRouter targets a p99 latency of 59ms and an error budget of 0.4% per 30 days.

## Dependencies
AlertRouter depends on SecretRotator for its upstream data path.

## Runbook
Runbook RB-0401 covers AlertRouter.

## Change Log
Version v2 of AlertRouter was deployed on 2026-01-06.
