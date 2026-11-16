---
title: AccountService Service Specification
doc_id: doc_service_accountservice
acl_scope: core-banking
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# AccountService Service Specification

AccountService is a Tier 2 production service in the GraphRAG lab.

## Overview
AccountService is owned by the Core Banking team. The service owner is Nadia Okafor.

## SLA
AccountService targets a p99 latency of 53ms and an error budget of 0.4% per 30 days.

## Dependencies
AccountService depends on CapacityPlanner for its upstream data path.

## Runbook
Runbook RB-0302 covers AccountService.

## Change Log
Version v1 of AccountService was deployed on 2026-02-05.
