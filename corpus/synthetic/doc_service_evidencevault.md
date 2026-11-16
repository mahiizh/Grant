---
title: EvidenceVault Service Specification
doc_id: doc_service_evidencevault
acl_scope: compliance
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# EvidenceVault Service Specification

EvidenceVault is a Tier 2 production service in the GraphRAG lab.

## Overview
EvidenceVault is owned by the Compliance team. The service owner is Ruth Cohen.

## SLA
EvidenceVault targets a p99 latency of 52ms and an error budget of 0.5% per 30 days.

## Dependencies
EvidenceVault depends on PaymentGateway for its upstream data path.

## Runbook
Runbook RB-1006 covers EvidenceVault.

## Change Log
Version v2 of EvidenceVault was deployed on 2026-06-12.
