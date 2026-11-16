---
title: AuditExporter Service Specification
doc_id: doc_service_auditexporter
acl_scope: compliance
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# AuditExporter Service Specification

AuditExporter is a Tier 2 production service in the GraphRAG lab.

## Overview
AuditExporter is owned by the Compliance team. The service owner is Ruth Cohen.

## SLA
AuditExporter targets a p99 latency of 31ms and an error budget of 0.2% per 30 days.

## Dependencies
AuditExporter depends on IngestionPipeline for its upstream data path.

## Runbook
Runbook RB-1003 covers AuditExporter.

## Change Log
Version v1 of AuditExporter was deployed on 2026-03-12.
