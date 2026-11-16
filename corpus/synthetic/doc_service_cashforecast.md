---
title: CashForecast Service Specification
doc_id: doc_service_cashforecast
acl_scope: treasury
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# CashForecast Service Specification

CashForecast is a Tier 1 production service in the GraphRAG lab.

## Overview
CashForecast is owned by the Treasury team. The service owner is Ravi Shah.

## SLA
CashForecast targets a p99 latency of 111ms and an error budget of 0.3% per 30 days.

## Dependencies
CashForecast depends on ExposureCalculator for its upstream data path.

## Runbook
Runbook RB-0801 covers CashForecast.

## Change Log
Version v2 of CashForecast was deployed on 2026-01-10.
