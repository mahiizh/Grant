---
title: ConsentRegistry Service Specification
doc_id: doc_service_consentregistry
acl_scope: compliance
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# ConsentRegistry Service Specification

ConsentRegistry is a Tier 2 production service in the GraphRAG lab.

## Overview
ConsentRegistry is owned by the Compliance team. The service owner is Diego Marin.

## SLA
ConsentRegistry targets a p99 latency of 24ms and an error budget of 0.1% per 30 days.

## Dependencies
ConsentRegistry depends on SchemaRegistry for its upstream data path.

## Runbook
Runbook RB-1002 covers ConsentRegistry.

## Change Log
Version v1 of ConsentRegistry was deployed on 2026-02-12.
