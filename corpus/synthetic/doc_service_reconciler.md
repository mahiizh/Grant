---
title: Reconciler Service Specification
doc_id: doc_service_reconciler
acl_scope: data-platform
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# Reconciler Service Specification

Reconciler is a Tier 2 production service in the GraphRAG lab.

## Overview
Reconciler is owned by the Data Platform team. The service owner is Priya Nair.

## SLA
Reconciler targets a p99 latency of 48ms and an error budget of 0.5% per 30 days.

## Dependencies
Reconciler depends on TokenizationAPI for its upstream data path.

## Runbook
Runbook RB-0105 covers Reconciler.

## Change Log
Version v1 of Reconciler was deployed on 2026-05-03.
