---
title: TokenizationAPI Service Specification
doc_id: doc_service_tokenizationapi
acl_scope: payments
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# TokenizationAPI Service Specification

TokenizationAPI is a Tier 2 production service in the GraphRAG lab.

## Overview
TokenizationAPI is owned by the Payments team. The service owner is Sofia Lind.

## SLA
TokenizationAPI targets a p99 latency of 68ms and an error budget of 0.2% per 30 days.

## Dependencies
TokenizationAPI depends on AlertRouter for its upstream data path.

## Runbook
Runbook RB-0206 covers TokenizationAPI.

## Change Log
Version v2 of TokenizationAPI was deployed on 2026-06-04.
