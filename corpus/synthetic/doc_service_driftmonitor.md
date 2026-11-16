---
title: DriftMonitor Service Specification
doc_id: doc_service_driftmonitor
acl_scope: ml-platform
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# DriftMonitor Service Specification

DriftMonitor is a Tier 2 production service in the GraphRAG lab.

## Overview
DriftMonitor is owned by the ML Platform team. The service owner is Iris Novak.

## SLA
DriftMonitor targets a p99 latency of 113ms and an error budget of 0.5% per 30 days.

## Dependencies
DriftMonitor depends on MacroService for its upstream data path.

## Runbook
Runbook RB-0605 covers DriftMonitor.

## Change Log
Version v1 of DriftMonitor was deployed on 2026-05-08.
