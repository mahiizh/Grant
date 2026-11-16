---
title: RegulatoryReporter Service Specification
doc_id: doc_service_regulatoryreporter
acl_scope: compliance
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# RegulatoryReporter Service Specification

RegulatoryReporter is a Tier 1 production service in the GraphRAG lab.

## Overview
RegulatoryReporter is owned by the Compliance team. The service owner is Helena Voss.

## SLA
RegulatoryReporter targets a p99 latency of 38ms and an error budget of 0.3% per 30 days.

## Dependencies
RegulatoryReporter depends on Reconciler for its upstream data path.

## Runbook
Runbook RB-1004 covers RegulatoryReporter.

## Change Log
Version v1 of RegulatoryReporter was deployed on 2026-04-12.
