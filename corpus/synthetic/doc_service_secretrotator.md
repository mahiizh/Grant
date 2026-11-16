---
title: SecretRotator Service Specification
doc_id: doc_service_secretrotator
acl_scope: security
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# SecretRotator Service Specification

SecretRotator is a Tier 2 production service in the GraphRAG lab.

## Overview
SecretRotator is owned by the Security team. The service owner is Liam Foster.

## SLA
SecretRotator targets a p99 latency of 79ms and an error budget of 0.1% per 30 days.

## Dependencies
SecretRotator depends on TrainingOrchestrator for its upstream data path.

## Runbook
Runbook RB-0502 covers SecretRotator.

## Change Log
Version v1 of SecretRotator was deployed on 2026-02-07.
