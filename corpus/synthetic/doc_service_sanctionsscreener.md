---
title: SanctionsScreener Service Specification
doc_id: doc_service_sanctionsscreener
acl_scope: compliance
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# SanctionsScreener Service Specification

SanctionsScreener is a Tier 2 production service in the GraphRAG lab.

## Overview
SanctionsScreener is owned by the Compliance team. The service owner is Diego Marin.

## SLA
SanctionsScreener targets a p99 latency of 45ms and an error budget of 0.4% per 30 days.

## Dependencies
SanctionsScreener depends on EmbeddingService for its upstream data path.

## Runbook
Runbook RB-1005 covers SanctionsScreener.

## Change Log
Version v1 of SanctionsScreener was deployed on 2026-05-12.
