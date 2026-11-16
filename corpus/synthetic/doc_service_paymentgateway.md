---
title: PaymentGateway Service Specification
doc_id: doc_service_paymentgateway
acl_scope: payments
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# PaymentGateway Service Specification

PaymentGateway is a Tier 1 production service in the GraphRAG lab.

## Overview
PaymentGateway is owned by the Payments team. The service owner is Elena Rostova.

## SLA
PaymentGateway targets a p99 latency of 33ms and an error budget of 0.2% per 30 days.

## Dependencies
PaymentGateway depends on AccountService for its upstream data path.

## Runbook
Runbook RB-0201 covers PaymentGateway.

## Change Log
Version v2 of PaymentGateway was deployed on 2026-01-04.
