---
title: CardVault Service Specification
doc_id: doc_service_cardvault
acl_scope: payments
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# CardVault Service Specification

CardVault is a Tier 1 production service in the GraphRAG lab.

## Overview
CardVault is owned by the Payments team. The service owner is Elena Rostova.

## SLA
CardVault targets a p99 latency of 54ms and an error budget of 0.5% per 30 days.

## Dependencies
CardVault depends on FxRateService for its upstream data path.

## Runbook
Runbook RB-0204 covers CardVault.

## Change Log
Version v1 of CardVault was deployed on 2026-04-04.
