---
title: AlertCorrelator Service Specification
doc_id: doc_service_alertcorrelator
acl_scope: risk
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# AlertCorrelator Service Specification

AlertCorrelator is a Tier 2 production service in the GraphRAG lab.

## Overview
AlertCorrelator is owned by the Risk team. The service owner is Felix Braun.

## SLA
AlertCorrelator targets a p99 latency of 32ms and an error budget of 0.3% per 30 days.

## Dependencies
AlertCorrelator depends on EvidenceVault for its upstream data path.

## Runbook
Runbook RB-0905 covers AlertCorrelator.

## Change Log
Version v1 of AlertCorrelator was deployed on 2026-05-11.
