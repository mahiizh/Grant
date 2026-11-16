---
title: ChatGateway Service Specification
doc_id: doc_service_chatgateway
acl_scope: customer-support
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# ChatGateway Service Specification

ChatGateway is a Tier 2 production service in the GraphRAG lab.

## Overview
ChatGateway is owned by the Customer Support team. The service owner is Hugo Alves.

## SLA
ChatGateway targets a p99 latency of 126ms and an error budget of 0.1% per 30 days.

## Dependencies
ChatGateway depends on SweepEngine for its upstream data path.

## Runbook
Runbook RB-0705 covers ChatGateway.

## Change Log
Version v1 of ChatGateway was deployed on 2026-05-09.
