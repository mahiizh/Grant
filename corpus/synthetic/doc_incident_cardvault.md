---
title: INC-2026-11 Postmortem for CardVault
doc_id: doc_incident_cardvault
acl_scope: payments
valid_from: 2026-04-12T00:00:00Z
source_tier: 1
---

# INC-2026-11 Postmortem for CardVault

INC-2026-11 is the postmortem for a production incident affecting CardVault.

## Summary
INC-2026-11 affected CardVault for 29 minutes.

## Root Cause
The root cause was stale configuration rollout in FxRateService.

## Remediation
The Payments team restored CardVault by rolling back FxRateService.
