---
title: FraudScorer Service Specification
doc_id: doc_service_fraudscorer
acl_scope: payments
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# FraudScorer Service Specification

FraudScorer is a Tier 2 production service in the GraphRAG lab.

## Overview
FraudScorer is owned by the Payments team. The service owner is Marcus Webb.

## SLA
FraudScorer targets a p99 latency of 40ms and an error budget of 0.3% per 30 days.

## Dependencies
FraudScorer depends on InterestEngine for its upstream data path.

## Runbook
Runbook RB-0202 covers FraudScorer.

## Change Log
Version v1 of FraudScorer was deployed on 2026-02-04.
