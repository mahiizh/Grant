---
title: LedgerCore Service Specification
doc_id: doc_service_ledgercore
acl_scope: core-banking
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# LedgerCore Service Specification

LedgerCore is a Tier 1 production service in the GraphRAG lab.

## Overview
LedgerCore is owned by the Core Banking team. The service owner is Dave Miller.

## SLA
LedgerCore targets a p99 latency of 46ms and an error budget of 0.3% per 30 days.

## Dependencies
LedgerCore depends on IncidentBot for its upstream data path.

## Runbook
Runbook RB-0301 covers LedgerCore.

## Change Log
Version v2 of LedgerCore was deployed on 2026-01-05.
