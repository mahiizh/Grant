---
title: ChaosRunner Service Specification
doc_id: doc_service_chaosrunner
acl_scope: sre
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# ChaosRunner Service Specification

ChaosRunner is a Tier 2 production service in the GraphRAG lab.

## Overview
ChaosRunner is owned by the Site Reliability Engineering team. The service owner is Omar Haddad.

## SLA
ChaosRunner targets a p99 latency of 94ms and an error budget of 0.4% per 30 days.

## Dependencies
ChaosRunner depends on FeatureStore for its upstream data path.

## Runbook
Runbook RB-0406 covers ChaosRunner.

## Change Log
Version v2 of ChaosRunner was deployed on 2026-06-06.
