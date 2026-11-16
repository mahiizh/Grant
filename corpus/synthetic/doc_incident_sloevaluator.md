---
title: INC-2026-13 Postmortem for SloEvaluator
doc_id: doc_incident_sloevaluator
acl_scope: sre
valid_from: 2026-04-12T00:00:00Z
source_tier: 1
---

# INC-2026-13 Postmortem for SloEvaluator

INC-2026-13 is the postmortem for a production incident affecting SloEvaluator.

## Summary
INC-2026-13 affected SloEvaluator for 51 minutes.

## Root Cause
The root cause was stale configuration rollout in PolicyEngine.

## Remediation
The Site Reliability Engineering team restored SloEvaluator by rolling back PolicyEngine.
