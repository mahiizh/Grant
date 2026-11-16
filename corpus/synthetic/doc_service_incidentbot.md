---
title: IncidentBot Service Specification
doc_id: doc_service_incidentbot
acl_scope: sre
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# IncidentBot Service Specification

IncidentBot is a Tier 2 production service in the GraphRAG lab.

## Overview
IncidentBot is owned by the Site Reliability Engineering team. The service owner is Grace Liu.

## SLA
IncidentBot targets a p99 latency of 66ms and an error budget of 0.5% per 30 days.

## Dependencies
IncidentBot depends on AuditLogger for its upstream data path.

## Runbook
Runbook RB-0402 covers IncidentBot.

## Change Log
Version v1 of IncidentBot was deployed on 2026-02-06.
