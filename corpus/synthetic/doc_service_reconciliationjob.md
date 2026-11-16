---
title: ReconciliationJob Service Specification
doc_id: doc_service_reconciliationjob
acl_scope: core-banking
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# ReconciliationJob Service Specification

ReconciliationJob is a Tier 2 production service in the GraphRAG lab.

## Overview
ReconciliationJob is owned by the Core Banking team. The service owner is Kenji Sato.

## SLA
ReconciliationJob targets a p99 latency of 81ms and an error budget of 0.3% per 30 days.

## Dependencies
ReconciliationJob depends on AccessBroker for its upstream data path.

## Runbook
Runbook RB-0306 covers ReconciliationJob.

## Change Log
Version v2 of ReconciliationJob was deployed on 2026-06-05.
