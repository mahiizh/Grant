---
title: EscalationEngine Service Specification
doc_id: doc_service_escalationengine
acl_scope: customer-support
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# EscalationEngine Service Specification

EscalationEngine is a Tier 1 production service in the GraphRAG lab.

## Overview
EscalationEngine is owned by the Customer Support team. The service owner is Zoe Bennett.

## SLA
EscalationEngine targets a p99 latency of 119ms and an error budget of 0.5% per 30 days.

## Dependencies
EscalationEngine depends on BalanceAggregator for its upstream data path.

## Runbook
Runbook RB-0704 covers EscalationEngine.

## Change Log
Version v1 of EscalationEngine was deployed on 2026-04-09.
