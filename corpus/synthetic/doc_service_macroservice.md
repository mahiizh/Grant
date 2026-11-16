---
title: MacroService Service Specification
doc_id: doc_service_macroservice
acl_scope: customer-support
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# MacroService Service Specification

MacroService is a Tier 2 production service in the GraphRAG lab.

## Overview
MacroService is owned by the Customer Support team. The service owner is Mei Tan.

## SLA
MacroService targets a p99 latency of 133ms and an error budget of 0.2% per 30 days.

## Dependencies
MacroService depends on CreditScorer for its upstream data path.

## Runbook
Runbook RB-0706 covers MacroService.

## Change Log
Version v2 of MacroService was deployed on 2026-06-09.
