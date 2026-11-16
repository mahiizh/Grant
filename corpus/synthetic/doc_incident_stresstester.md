---
title: INC-2026-18 Postmortem for StressTester
doc_id: doc_incident_stresstester
acl_scope: risk
valid_from: 2026-04-12T00:00:00Z
source_tier: 1
---

# INC-2026-18 Postmortem for StressTester

INC-2026-18 is the postmortem for a production incident affecting StressTester.

## Summary
INC-2026-18 affected StressTester for 106 minutes.

## Root Cause
The root cause was connection-pool exhaustion in SanctionsScreener.

## Remediation
The Risk team restored StressTester by rolling back SanctionsScreener.
