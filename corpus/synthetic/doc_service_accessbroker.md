---
title: AccessBroker Service Specification
doc_id: doc_service_accessbroker
acl_scope: security
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# AccessBroker Service Specification

AccessBroker is a Tier 1 production service in the GraphRAG lab.

## Overview
AccessBroker is owned by the Security team. The service owner is Maya Singh.

## SLA
AccessBroker targets a p99 latency of 72ms and an error budget of 0.5% per 30 days.

## Dependencies
AccessBroker depends on ModelRegistry for its upstream data path.

## Runbook
Runbook RB-0501 covers AccessBroker.

## Change Log
Version v2 of AccessBroker was deployed on 2026-01-07.
