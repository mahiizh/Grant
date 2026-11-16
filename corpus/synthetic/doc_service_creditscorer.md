---
title: CreditScorer Service Specification
doc_id: doc_service_creditscorer
acl_scope: risk
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# CreditScorer Service Specification

CreditScorer is a Tier 1 production service in the GraphRAG lab.

## Overview
CreditScorer is owned by the Risk team. The service owner is Amara Diallo.

## SLA
CreditScorer targets a p99 latency of 124ms and an error budget of 0.4% per 30 days.

## Dependencies
CreditScorer depends on ConsentRegistry for its upstream data path.

## Runbook
Runbook RB-0901 covers CreditScorer.

## Change Log
Version v2 of CreditScorer was deployed on 2026-01-11.
