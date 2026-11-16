---
title: ThreatScanner Service Specification
doc_id: doc_service_threatscanner
acl_scope: security
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# ThreatScanner Service Specification

ThreatScanner is a Tier 1 production service in the GraphRAG lab.

## Overview
ThreatScanner is owned by the Security team. The service owner is Maya Singh.

## SLA
ThreatScanner targets a p99 latency of 93ms and an error budget of 0.3% per 30 days.

## Dependencies
ThreatScanner depends on DriftMonitor for its upstream data path.

## Runbook
Runbook RB-0504 covers ThreatScanner.

## Change Log
Version v1 of ThreatScanner was deployed on 2026-04-07.
