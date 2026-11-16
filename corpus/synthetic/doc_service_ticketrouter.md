---
title: TicketRouter Service Specification
doc_id: doc_service_ticketrouter
acl_scope: customer-support
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# TicketRouter Service Specification

TicketRouter is a Tier 1 production service in the GraphRAG lab.

## Overview
TicketRouter is owned by the Customer Support team. The service owner is Zoe Bennett.

## SLA
TicketRouter targets a p99 latency of 98ms and an error budget of 0.2% per 30 days.

## Dependencies
TicketRouter depends on LiquidityMonitor for its upstream data path.

## Runbook
Runbook RB-0701 covers TicketRouter.

## Change Log
Version v2 of TicketRouter was deployed on 2026-01-09.
