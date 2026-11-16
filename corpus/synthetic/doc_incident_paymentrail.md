---
title: INC-2026-17 Postmortem for PaymentRail
doc_id: doc_incident_paymentrail
acl_scope: treasury
valid_from: 2026-04-12T00:00:00Z
source_tier: 1
---

# INC-2026-17 Postmortem for PaymentRail

INC-2026-17 is the postmortem for a production incident affecting PaymentRail.

## Summary
INC-2026-17 affected PaymentRail for 95 minutes.

## Root Cause
The root cause was stale configuration rollout in AlertCorrelator.

## Remediation
The Treasury team restored PaymentRail by rolling back AlertCorrelator.
