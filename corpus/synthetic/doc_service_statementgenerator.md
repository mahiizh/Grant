---
title: StatementGenerator Service Specification
doc_id: doc_service_statementgenerator
acl_scope: core-banking
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# StatementGenerator Service Specification

StatementGenerator is a Tier 1 production service in the GraphRAG lab.

## Overview
StatementGenerator is owned by the Core Banking team. The service owner is Dave Miller.

## SLA
StatementGenerator targets a p99 latency of 67ms and an error budget of 0.1% per 30 days.

## Dependencies
StatementGenerator depends on OnCallScheduler for its upstream data path.

## Runbook
Runbook RB-0304 covers StatementGenerator.

## Change Log
Version v1 of StatementGenerator was deployed on 2026-04-05.
