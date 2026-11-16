---
title: StressTester Service Specification
doc_id: doc_service_stresstester
acl_scope: risk
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# StressTester Service Specification

StressTester is a Tier 1 production service in the GraphRAG lab.

## Overview
StressTester is owned by the Risk team. The service owner is Amara Diallo.

## SLA
StressTester targets a p99 latency of 25ms and an error budget of 0.2% per 30 days.

## Dependencies
StressTester depends on SanctionsScreener for its upstream data path.

## Runbook
Runbook RB-0904 covers StressTester.

## Change Log
Version v1 of StressTester was deployed on 2026-04-11.
