---
title: INC-2026-12 Postmortem for StatementGenerator
doc_id: doc_incident_statementgenerator
acl_scope: core-banking
valid_from: 2026-04-12T00:00:00Z
source_tier: 1
---

# INC-2026-12 Postmortem for StatementGenerator

INC-2026-12 is the postmortem for a production incident affecting StatementGenerator.

## Summary
INC-2026-12 affected StatementGenerator for 40 minutes.

## Root Cause
The root cause was connection-pool exhaustion in OnCallScheduler.

## Remediation
The Core Banking team restored StatementGenerator by rolling back OnCallScheduler.
