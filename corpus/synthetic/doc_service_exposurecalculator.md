---
title: ExposureCalculator Service Specification
doc_id: doc_service_exposurecalculator
acl_scope: risk
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# ExposureCalculator Service Specification

ExposureCalculator is a Tier 2 production service in the GraphRAG lab.

## Overview
ExposureCalculator is owned by the Risk team. The service owner is Felix Braun.

## SLA
ExposureCalculator targets a p99 latency of 131ms and an error budget of 0.5% per 30 days.

## Dependencies
ExposureCalculator depends on AuditExporter for its upstream data path.

## Runbook
Runbook RB-0902 covers ExposureCalculator.

## Change Log
Version v1 of ExposureCalculator was deployed on 2026-02-11.
