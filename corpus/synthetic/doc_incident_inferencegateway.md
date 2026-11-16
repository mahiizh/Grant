---
title: INC-2026-15 Postmortem for InferenceGateway
doc_id: doc_incident_inferencegateway
acl_scope: ml-platform
valid_from: 2026-04-12T00:00:00Z
source_tier: 1
---

# INC-2026-15 Postmortem for InferenceGateway

INC-2026-15 is the postmortem for a production incident affecting InferenceGateway.

## Summary
INC-2026-15 affected InferenceGateway for 73 minutes.

## Root Cause
The root cause was stale configuration rollout in ChatGateway.

## Remediation
The ML Platform team restored InferenceGateway by rolling back ChatGateway.
