---
title: SchemaRegistry Service Specification
doc_id: doc_service_schemaregistry
acl_scope: data-platform
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# SchemaRegistry Service Specification

SchemaRegistry is a Tier 2 production service in the GraphRAG lab.

## Overview
SchemaRegistry is owned by the Data Platform team. The service owner is Tomas Vidal.

## SLA
SchemaRegistry targets a p99 latency of 34ms and an error budget of 0.3% per 30 days.

## Dependencies
SchemaRegistry depends on CardVault for its upstream data path.

## Runbook
Runbook RB-0103 covers SchemaRegistry.

## Change Log
Version v1 of SchemaRegistry was deployed on 2026-03-03.
