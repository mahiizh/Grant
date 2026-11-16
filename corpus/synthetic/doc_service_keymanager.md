---
title: KeyManager Service Specification
doc_id: doc_service_keymanager
acl_scope: security
valid_from: 2026-02-01T00:00:00Z
source_tier: 1
---

# KeyManager Service Specification

KeyManager is a Tier 2 production service in the GraphRAG lab.

## Overview
KeyManager is owned by the Security team. The service owner is Anika Rao.

## SLA
KeyManager targets a p99 latency of 107ms and an error budget of 0.5% per 30 days.

## Dependencies
KeyManager depends on TicketRouter for its upstream data path.

## Runbook
Runbook RB-0506 covers KeyManager.

## Change Log
Version v2 of KeyManager was deployed on 2026-06-07.
