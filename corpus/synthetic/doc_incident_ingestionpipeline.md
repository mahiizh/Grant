---
title: INC-2026-10 Postmortem for IngestionPipeline
doc_id: doc_incident_ingestionpipeline
acl_scope: data-platform
valid_from: 2026-04-12T00:00:00Z
source_tier: 1
---

# INC-2026-10 Postmortem for IngestionPipeline

INC-2026-10 is the postmortem for a production incident affecting IngestionPipeline.

## Summary
INC-2026-10 affected IngestionPipeline for 18 minutes.

## Root Cause
The root cause was connection-pool exhaustion in RefundService.

## Remediation
The Data Platform team restored IngestionPipeline by rolling back RefundService.
