---
title: INC-2026-19 Postmortem for RegulatoryReporter
doc_id: doc_incident_regulatoryreporter
acl_scope: compliance
valid_from: 2026-04-12T00:00:00Z
source_tier: 1
---

# INC-2026-19 Postmortem for RegulatoryReporter

INC-2026-19 is the postmortem for a production incident affecting RegulatoryReporter.

## Summary
INC-2026-19 affected RegulatoryReporter for 27 minutes.

## Root Cause
The root cause was stale configuration rollout in Reconciler.

## Remediation
The Compliance team restored RegulatoryReporter by rolling back Reconciler.
