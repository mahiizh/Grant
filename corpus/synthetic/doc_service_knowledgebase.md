---
title: KnowledgeBase Service Specification
doc_id: doc_service_knowledgebase
acl_scope: customer-support
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# KnowledgeBase Service Specification

KnowledgeBase is a Tier 2 production service in the GraphRAG lab.

## Overview
KnowledgeBase is owned by the Customer Support team. The service owner is Hugo Alves.

## SLA
KnowledgeBase targets a p99 latency of 105ms and an error budget of 0.3% per 30 days.

## Dependencies
KnowledgeBase depends on FxHedging for its upstream data path.

## Runbook
Runbook RB-0702 covers KnowledgeBase.

## Change Log
Version v1 of KnowledgeBase was deployed on 2026-02-09.
