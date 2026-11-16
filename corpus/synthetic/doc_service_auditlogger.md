---
title: AuditLogger Service Specification
doc_id: doc_service_auditlogger
acl_scope: security
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# AuditLogger Service Specification

AuditLogger is a Tier 2 production service in the GraphRAG lab.

## Overview
AuditLogger is owned by the Security team. The service owner is Anika Rao.

## SLA
AuditLogger targets a p99 latency of 86ms and an error budget of 0.2% per 30 days.

## Dependencies
AuditLogger depends on InferenceGateway for its upstream data path.

## Runbook
Runbook RB-0503 covers AuditLogger.

## Change Log
Version v1 of AuditLogger was deployed on 2026-03-07.
