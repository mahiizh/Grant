---
title: ModelValidator Service Specification
doc_id: doc_service_modelvalidator
acl_scope: risk
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# ModelValidator Service Specification

ModelValidator is a Tier 2 production service in the GraphRAG lab.

## Overview
ModelValidator is owned by the Risk team. The service owner is Sana Iqbal.

## SLA
ModelValidator targets a p99 latency of 39ms and an error budget of 0.4% per 30 days.

## Dependencies
ModelValidator depends on EventStream for its upstream data path.

## Runbook
Runbook RB-0906 covers ModelValidator.

## Change Log
Version v2 of ModelValidator was deployed on 2026-06-11.
